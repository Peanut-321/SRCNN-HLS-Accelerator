"""Explicit Q20.12 V3 memory-to-memory benchmark; no hardware action on import."""
import hashlib
import importlib.util
import json
import shutil
import statistics
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ACTIVE_RUNNERS = []


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def instrument(source):
    """Add only an output-ready timestamp; keep original recovery and checks."""
    marker = '            output = np.asarray(destination).copy()\n'
    field = '"host_allocate_to_compare_s": time.perf_counter() - begin,'
    if source.count(marker) != 1 or source.count(field) != 1:
        raise ValueError('Unexpected host source; refusing to instrument')
    source = source.replace(marker, marker + '            memory_to_memory_seconds = time.perf_counter() - begin\n')
    source = source.replace(field, field + '\n                    "memory_to_memory_seconds": memory_to_memory_seconds,')
    compile(source, '<timing-instrumented-host>', 'exec')
    return source


def run(project='.', repeats=3, cpu_directory=None):
    if repeats != 3:
        raise ValueError('This evidence protocol uses exactly three measured repeats')
    project = Path(project).resolve()
    kit = project / 'q20_12_return_board_check'
    delivery = project / 'srcnn_q20_12_v3_resetfix'
    hashes = json.loads((kit / 'kit_checksums.json').read_text())
    for name, expected in hashes.items():
        path = (kit / name.replace('\\', '/')).resolve()
        if not path.is_relative_to(kit) or sha(path) != expected:
            raise ValueError('Kit checksum mismatch: ' + name)
    cpu_dir = Path(cpu_directory).resolve() if cpu_directory is not None else kit / 'cpu_results_20260817T063705_562593Z'
    cpu = json.loads((cpu_dir / 'cpu_results.json').read_text())
    if cpu['status'] != 'PASS' or cpu['case'] != 'butterfly' or len(cpu['runs']) != 4:
        raise ValueError('Expected audited Butterfly CPU record is missing')
    expected = np.load(kit / 'cases/butterfly/expected.npy', allow_pickle=False)
    for i, result in enumerate(cpu['runs']):
        if result['phase'] != ('warmup' if i == 0 else 'repeat'):
            raise ValueError('Unexpected CPU schedule')
        if not np.array_equal(np.fromfile(cpu_dir / f'output_{i}.bin', dtype='<u4'), expected):
            raise ValueError('CPU saved output does not match reference')
    cpu_source = (kit / 'cpu_reference.cpp').read_text()
    start = 'auto start=std::chrono::steady_clock::now();'
    stop = 'double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();'
    if cpu_source.count(start) != 1 or cpu_source.count(stop) != 1:
        raise ValueError('Unexpected CPU timer implementation')
    if not (cpu_source.index('auto current=read') < cpu_source.index(start) < cpu_source.index(stop) < cpu_source.index('std::ofstream out')):
        raise ValueError('CPU timing boundary is not as expected')
    sys.path.insert(0, str(delivery))
    import aero_board_test
    if Path(aero_board_test.__file__).resolve() != delivery / 'aero_board_test.py':
        raise ValueError('Wrong delivery module loaded; do not mix formats')
    _, manifest, host, _ = aero_board_test.verify_delivery(delivery)
    if manifest['profile'] != 'q20_12' or manifest.get('deployment_revision') != 'HPM1_HPC0_B000_B001_RESETFIX_V3':
        raise ValueError('Only verified Q20.12 V3 is supported')
    original = Path(host.__file__).read_text()
    modified = instrument(original)
    timed = types.ModuleType('timed_v3_host')
    timed.__file__ = str(host.__file__)
    exec(compile(modified, '<timing-instrumented-host>', 'exec'), timed.__dict__)
    # verify_delivery binds the original host to the validated V3 manifest.
    # Re-executing the source restores its historical default hash constants;
    # explicitly carry the verified binding into the timing-only module.
    timed.BIT_SHA256 = manifest['files']['srcnn_axis_255x255.bit']
    timed.HWH_SHA256 = manifest['files']['srcnn_axis_255x255.hwh']
    if timed.BIT_SHA256 != host.BIT_SHA256 or timed.HWH_SHA256 != host.HWH_SHA256:
        raise ValueError('Verified host hash binding differs from delivery manifest')
    codec_path = kit / 'srcnn_q20_12_bundle.py'
    spec = importlib.util.spec_from_file_location('benchmark_q20_codec', codec_path)
    codec = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(codec)
    _, arrays = codec.read_bundle(kit / 'cases/butterfly')
    out = kit / ('memory_to_memory_results_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    out.mkdir(exist_ok=False)
    shutil.copyfile(kit / 'cpu_reference.cpp', out / 'cpu_reference.cpp')
    shutil.copyfile(cpu_dir / 'cpu_results.json', out / 'original_cpu_results.json')
    (out / 'timed_v3_host.py').write_text(modified, encoding='utf-8')
    report = {
        'status': 'RUNNING', 'case': 'butterfly', 'profile': 'q20_12',
        'source_commit': manifest['source_commit'], 'board_clock_timestamp_untrusted': True,
        'boundary': 'Input and model already resident in host memory -> complete output resident in host memory. File IO, correctness comparison, compilation and initial overlay loading excluded.',
        'cpu_scope': 'Existing single-thread scalar C++ GCC -O3 record: includes intermediate allocations and all three convolutions. Input/model reads occur before timer; output file write after timer.',
        'fpga_scope': 'Includes contiguous-buffer allocation, input/model copies, cache flush, DMA reset and control, FPGA model load and compute, DMA, output invalidation and host copy. Excludes comparison and subsequent buffer cleanup.',
        'limitation': 'Functional memory-to-memory boundaries, not identical internal operations. CPU is a scalar reference baseline, not an optimized NEON/multithreaded library. CPU/FPGA were measured sequentially, not concurrently; CPU clock and thermal state were not controlled. No isolated kernel/model/DMA timing is claimed.',
        'cpu_record_sha256': sha(cpu_dir / 'cpu_results.json'),
        'cpu_source_sha256': sha(kit / 'cpu_reference.cpp'),
        'cpu_executable_sha256': sha(cpu_dir / 'cpu_reference'),
        'original_host_sha256': sha(host.__file__),
        'bound_bit_sha256': timed.BIT_SHA256,
        'bound_hwh_sha256': timed.HWH_SHA256,
        'instrumented_host_sha256': hashlib.sha256(modified.encode('utf-8')).hexdigest(),
        'runs': []}
    runner = None
    try:
        runner = timed.Runner(delivery / 'srcnn_axis_255x255.bit', 120)
        ACTIVE_RUNNERS.append(runner)
        for i in range(repeats + 1):
            result, output = runner.run(arrays)
            if not np.array_equal(output, expected):
                raise AssertionError('FPGA output differs from audited reference')
            result['phase'] = 'warmup' if i == 0 else 'repeat'
            report['runs'].append(result)
            np.save(out / f'fpga_output_{i}.npy', output, allow_pickle=False)
            (out / 'benchmark.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print('FPGA PASS', result['phase'], 'memory-to-memory seconds:', result['memory_to_memory_seconds'], flush=True)
        cpu_median = statistics.median(r['compute_seconds'] for r in cpu['runs'][1:])
        fpga_median = statistics.median(r['memory_to_memory_seconds'] for r in report['runs'][1:])
        report.update(status='PASS', cpu_median_seconds=cpu_median,
                      fpga_median_seconds=fpga_median,
                      scalar_cpu_baseline_time_ratio=cpu_median / fpga_median)
        ACTIVE_RUNNERS.remove(runner)
        print('CPU scalar baseline median:', cpu_median, flush=True)
        print('FPGA memory-to-memory median:', fpga_median, flush=True)
        print('Time ratio relative to scalar CPU baseline:', cpu_median / fpga_median, flush=True)
    except BaseException as error:
        report.update(status='FAIL_OR_INTERRUPTED', error=repr(error))
        if runner is None:
            print('Initialization failed; no frame transfer was started. Inspect the traceback before retrying.', flush=True)
        else:
            print('STOP. Keep this kernel alive after a hardware failure; do not start another board run.', flush=True)
        raise
    finally:
        (out / 'benchmark.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('Saved:', out, flush=True)
    archive = shutil.make_archive(str(out), 'zip', root_dir=str(out))
    print('Download results archive:', archive, flush=True)
    return out
