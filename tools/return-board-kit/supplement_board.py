"""Explicit, persistent-notebook V3 tests. No FPGA action on import."""
import hashlib, importlib, json, platform, shutil, statistics, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

ACTIVE_RUNNERS=[]

def check_kit(kit):
    kit=Path(kit).resolve()
    hashes=json.loads((kit/'kit_checksums.json').read_text())
    for rel,expected in hashes.items():
        p=(kit/rel.replace('\\','/')).resolve()
        if not p.is_relative_to(kit) or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
            raise ValueError('Kit checksum mismatch: '+rel)
    return kit

def run_images(delivery,kit):
    kit=check_kit(kit);delivery=Path(delivery).resolve()
    sys.path.insert(0,str(delivery))
    import aero_board_test
    if Path(aero_board_test.__file__).resolve()!=delivery/'aero_board_test.py':
        raise ValueError('Restart notebook kernel before changing deliveries')
    _,manifest,host,_=aero_board_test.verify_delivery(delivery)
    if manifest['profile']!='q20_12' or manifest.get('deployment_revision')!='HPM1_HPC0_B000_B001_RESETFIX_V3':
        raise ValueError('Only approved Q20.12 V3 delivery is supported')
    codec=importlib.import_module('srcnn_q20_12_bundle')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    out=kit/('additional_board_results_'+stamp);out.mkdir(exist_ok=False)
    report={'status':'RUNNING','profile':'q20_12','source_commit':manifest['source_commit'],
        'scope':'14 supplied images, official model, no SRCNN reset between frames; DMA reset per frame',
        'measurement':'host transfer start to done including model load and DMA; not kernel-only',
        'board_clock_timestamp_untrusted':True,'runs':[]}
    runner=None
    try:
        runner=host.Runner(delivery/'srcnn_axis_255x255.bit',120)
        ACTIVE_RUNNERS.append(runner)
        names=[c['name'] for c in json.loads((kit/'offline_metrics.json').read_text())['cases']]
        for name in names:
            _,arrays=codec.read_bundle(kit/'cases'/name)
            result,output=runner.run(arrays)
            result['case']=name
            report['runs'].append(result)
            np.save(out/(name+'.npy'),output,allow_pickle=False)
            (out/'board_results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print('PASS',name,'65025 exact words',result['transfer_start_to_done_s'],flush=True)
        report['status']='PASS'
        ACTIVE_RUNNERS.remove(runner)
    except BaseException as error:
        report.update(status='FAIL_OR_INTERRUPTED',error=repr(error))
        if runner is not None: report['buffers_retained']=len(runner.quarantined)
        print('STOP. Do not start another kernel/run after a hardware failure.',flush=True)
        raise
    finally:
        (out/'board_results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('Saved:',out,flush=True)
    return out

def run_cpu(kit,case='butterfly',repeats=3):
    kit=check_kit(kit)
    if repeats<1 or repeats>10:raise ValueError('repeats must be 1..10')
    if case not in [c['name'] for c in json.loads((kit/'offline_metrics.json').read_text())['cases']]:raise ValueError('Unknown case')
    out=kit/('cpu_results_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));out.mkdir(exist_ok=False)
    compiler=shutil.which('g++')
    report={'status':'RUNNING','platform':platform.platform(),'machine':platform.machine(),
        'case':case,'implementation':'scalar C++ Q20.12 exact arithmetic, single thread, GCC -O3',
        'measurement':'CPU compute-only; file IO excluded. FPGA available metric includes model load and DMA. Not identical internal boundaries; do not silently equate.',
        'runs':[],'cpuinfo':Path('/proc/cpuinfo').read_text() if Path('/proc/cpuinfo').exists() else 'unavailable'}
    try:
        if not compiler:
            report['status']='SKIPPED_NO_COMPILER'
            print('No g++ installed. Do not install packages during this urgent test.',flush=True)
            return out
        exe=out/'cpu_reference'
        report['compiler']=subprocess.check_output([compiler,'--version'],text=True)
        build=subprocess.run([compiler,'-O3','-std=c++14',str(kit/'cpu_reference.cpp'),'-o',str(exe)],capture_output=True,text=True,timeout=60)
        report['compiler_log']=build.stdout+build.stderr
        if build.returncode:raise RuntimeError('CPU compilation failed: '+report['compiler_log'])
        expected=np.load(kit/'cases'/case/'expected.npy',allow_pickle=False)
        for i in range(repeats+1):
            target=out/('output_'+str(i)+'.bin')
            wall=time.perf_counter()
            proc=subprocess.run([str(exe),str(kit/'cases'/case/'input.bin'),str(kit/'cases'/case/'model.bin'),str(target)],capture_output=True,text=True,timeout=180)
            external=time.perf_counter()-wall
            if proc.returncode:raise RuntimeError(proc.stderr)
            actual=np.fromfile(target,dtype='<u4')
            if not np.array_equal(actual,expected):raise AssertionError('CPU reference differs from offline expected')
            result={'phase':'warmup' if i==0 else 'repeat','compute_seconds':float(proc.stdout.strip()),'process_including_file_io_seconds':external,'exact_match':True}
            report['runs'].append(result)
            print('CPU PASS',result,flush=True)
            (out/'cpu_results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        report['median_compute_seconds']=statistics.median(r['compute_seconds'] for r in report['runs'] if r['phase']=='repeat')
        report['status']='PASS'
    except BaseException as error:
        report.update(status='FAIL_OR_INTERRUPTED',error=repr(error));raise
    finally:
        (out/'cpu_results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('Saved:',out,flush=True)
    return out
