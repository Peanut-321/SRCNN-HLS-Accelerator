"""Prepare additional V3 Q20.12 cases; never programs hardware."""
import argparse, copy, hashlib, json, shutil, zipfile
from pathlib import Path
import numpy as np
from deployment_numeric import metrics, infer
from precision_numeric import FixedFormat, infer_fixed
import srcnn_q20_12_bundle as codec

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--golden',type=Path,required=True)
    parser.add_argument('--delivery',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    a=parser.parse_args()
    if a.out.exists(): raise ValueError('Output already exists; do not overwrite')
    model=np.concatenate([np.fromfile(a.golden/f'src/weights/conv{i}_{kind}_3x_flp.bin',dtype='<f4') for i in (1,2,3) for kind in ('weights','biases')])
    codec.validate_float_model(model)
    fmt=FixedFormat(32,12)
    raw_model=codec.encode_values(model)
    template, original=codec.read_bundle(a.delivery/'butterfly')
    if not np.array_equal(raw_model,original['model']): raise ValueError('Official model differs from V3 Butterfly bundle')
    files=sorted((a.golden/'test/set5').glob('*_LR_u8.bin'))+sorted((a.golden/'test/set14').glob('*_LR_u8.bin'))
    if len(files)!=14: raise ValueError(f'Expected supplied 14 images, got {len(files)}')
    a.out.mkdir(parents=True)
    for name in ('deployment_numeric.py','precision_numeric.py','srcnn_q20_12_bundle.py','supplement_board.py','cpu_reference.cpp'):
        shutil.copyfile(Path(__file__).with_name(name),a.out/name)
    summary={'status':'OFFLINE_PREPARED_NOT_BOARD_TESTED','profile':'q20_12','cases':[],
        'reference_branch':'origin/optimize/official-q20-12','reference_accumulator_bits':[31,37,44],
        'metric_policy':{'peak':1,'crop':0,'clamp':False},'source_asset_hashes':{}}
    for f in files:
        name=f.name.split('_3x_')[0]
        image=np.fromfile(f,dtype='u1').reshape(255,255).astype(np.float32)/np.float32(255)
        gtpath=f.with_name(f.name.replace('LR_u8','GT_u8'))
        gt=np.fromfile(gtpath,dtype='u1').reshape(255,255).astype(np.float32)/np.float32(255)
        inp=codec.encode_values(image).reshape(-1)
        layers,diag=infer_fixed(inp.view('<i4').reshape(255,255),raw_model.view('<i4'),fmt,accumulator_bits=[31,37,44])
        if any(d['accumulator_saturations'] or d['data_saturations'] for d in diag): raise ValueError('Unexpected saturation: '+name)
        expected=layers[-1].astype('<i4').reshape(-1).view('<u4')
        if name=='butterfly':
            for key,val in [('input',inp),('expected',expected)]:
                if not np.array_equal(val,original[key]): raise ValueError('V3 anchor mismatch: '+key)
        floating,_=infer(image,model,fixed=False)
        actual=expected.view('<i4').reshape(255,255).astype(np.float64)/4096
        out=a.out/'cases'/name;out.mkdir(parents=True)
        manifest=copy.deepcopy(template)
        manifest['sources']={};manifest['status']='ADDITIONAL_CASE_OFFLINE_PREPARED_NOT_BOARD_VALIDATED'
        manifest['reference']='independent integer MAC, V3 31/37/44-bit accumulator contract; Butterfly anchor matched'
        manifest['artifacts']={}
        for key,val in [('input',inp),('model',raw_model),('expected',expected)]:
            np.save(out/(key+'.npy'),val,allow_pickle=False)
            val.tofile(out/(key+'.bin'))
            manifest['artifacts'][key+'.npy']={'sha256':sha(out/(key+'.npy')),'words':val.size}
        np.save(out/'ground_truth.npy',gt,allow_pickle=False)
        np.save(out/'float_output.npy',floating[-1][0],allow_pickle=False)
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        codec.read_bundle(out)
        item={'name':name,'dataset':f.parent.name,'float_vs_gt':metrics(floating[-1][0],gt,1),
              'fixed_vs_gt':metrics(actual,gt,1),'fixed_vs_float':metrics(actual,floating[-1][0],1),
              'saturation_diagnostics':diag}
        summary['cases'].append(item)
        summary['source_asset_hashes'][str(f)]=sha(f)
        summary['source_asset_hashes'][str(gtpath)]=sha(gtpath)
        (a.out/'offline_metrics.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        print('PREPARED',name,'fixed-vs-float',item['fixed_vs_float']['psnr_db'],flush=True)
    summary['min_fixed_vs_float_psnr_db']=min(c['fixed_vs_float']['psnr_db'] for c in summary['cases'])
    summary['max_absolute_reconstruction_psnr_delta_db']=max(abs(c['fixed_vs_gt']['psnr_db']-c['float_vs_gt']['psnr_db']) for c in summary['cases'])
    (a.out/'offline_metrics.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    summary_path=a.out/'kit_checksums.json'
    summary_path.write_text(json.dumps({p.relative_to(a.out).as_posix():sha(p) for p in sorted(a.out.rglob('*')) if p.is_file() and p!=summary_path},indent=2),encoding='utf-8')
    with zipfile.ZipFile(a.out.with_suffix('.zip'),'x',zipfile.ZIP_DEFLATED) as z:
        for p in a.out.rglob('*'):
            if p.is_file():z.write(p,(Path(a.out.name)/p.relative_to(a.out)).as_posix())
    print('READY',a.out.with_suffix('.zip'),flush=True)

if __name__=='__main__': main()
