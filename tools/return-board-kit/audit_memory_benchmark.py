"""Independently check downloaded timing evidence; never execute board code."""
import hashlib
import importlib.util
import io
import json
import shutil
import statistics
import zipfile
from pathlib import Path

import numpy as np


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    source = Path('C:/Users/aeroc/Desktop/文件/EE/2026S2/90096/Project')
    destination = Path('results/srcnn-board/q20_12/return-board-2026-10-12')
    archive_name = 'memory_to_memory_results_20260817T070820_275461Z.zip'
    kit = Path('.codex-build/q20_12_return_board_check')
    spec = importlib.util.spec_from_file_location('timing_script', Path(__file__).with_name('benchmark_memory_to_memory.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with zipfile.ZipFile(source / archive_name) as z, zipfile.ZipFile(destination / 'cpu_results_20260817T063705_562593Z.zip') as cpu_zip:
        assert z.testzip() is None and len(z.namelist()) == 8
        report = json.loads(z.read('benchmark.json'))
        assert report['status'] == 'PASS' and report['profile'] == 'q20_12' and report['case'] == 'butterfly'
        assert len(report['runs']) == 4
        expected = np.load(kit / 'cases/butterfly/expected.npy', allow_pickle=False)
        for i, run in enumerate(report['runs']):
            actual = np.load(io.BytesIO(z.read(f'fpga_output_{i}.npy')), allow_pickle=False)
            assert actual.shape == expected.shape and actual.dtype == expected.dtype
            assert np.array_equal(actual, expected) and actual.size == 65025
            assert run['status'] == 'PASS' and run['exact_match'] and run['words'] == 65025
            assert run['phase'] == ('warmup' if i == 0 else 'repeat')
            assert 0 < run['transfer_start_to_done_s'] <= run['memory_to_memory_seconds'] <= run['host_allocate_to_compare_s']
            for key in ('bit', 'hwh'):
                assert run['identity'][key + '_sha256'] == report['bound_' + key + '_sha256']
        assert z.read('original_cpu_results.json') == cpu_zip.read('cpu_results.json')
        assert digest(z.read('original_cpu_results.json')) == report['cpu_record_sha256']
        assert digest(cpu_zip.read('cpu_reference')) == report['cpu_executable_sha256']
        assert z.read('cpu_reference.cpp') == (kit / 'cpu_reference.cpp').read_bytes()
        assert digest(z.read('cpu_reference.cpp')) == report['cpu_source_sha256']
        cpu = json.loads(z.read('original_cpu_results.json'))
        cpu_median = statistics.median(r['compute_seconds'] for r in cpu['runs'][1:])
        fpga_median = statistics.median(r['memory_to_memory_seconds'] for r in report['runs'][1:])
        assert cpu_median == report['cpu_median_seconds']
        assert fpga_median == report['fpga_median_seconds']
        assert cpu_median / fpga_median == report['scalar_cpu_baseline_time_ratio']
        host_path = source / 'srcnn_q20_12_v3_resetfix/srcnn_axis_host.py'
        assert digest(host_path.read_bytes()) == report['original_host_sha256']
        assert z.read('timed_v3_host.py').decode() == module.instrument(host_path.read_text())
        assert digest(z.read('timed_v3_host.py')) == report['instrumented_host_sha256']
        for key, suffix in [('bit', '.bit'), ('hwh', '.hwh')]:
            assert digest((host_path.parent / ('srcnn_axis_255x255' + suffix)).read_bytes()) == report['bound_' + key + '_sha256']
    nb = json.loads((source / 'Untitled3 (1).ipynb').read_text(encoding='utf-8'))
    success_cells = [c for c in nb['cells'] if c.get('execution_count') == 5]
    assert len(success_cells) == 1
    assert not any(o['output_type'] == 'error' for o in success_cells[0]['outputs'])
    text = ''.join(''.join(o.get('text', [])) for o in success_cells[0]['outputs'] if o['output_type'] == 'stream')
    assert text.count('FPGA PASS') == 4
    assert str(fpga_median) in text and str(cpu_median / fpga_median) in text
    for name in [archive_name, 'Untitled3 (1).ipynb']:
        target = destination / name
        if target.exists():
            assert target.read_bytes() == (source / name).read_bytes()
        else:
            shutil.copyfile(source / name, target)
    audit = {'status': 'PASS', 'audit_date': '2026-10-12', 'verified_output_words': 4 * 65025,
             'cpu_median_seconds': cpu_median, 'fpga_memory_to_memory_median_seconds': fpga_median,
             'ratio_relative_to_scalar_single_thread_cpu_baseline': cpu_median / fpga_median,
             'scope': report['boundary'], 'limitations': report['limitation'],
             'notebook': 'Original error and successful retry records preserved unchanged.',
             'archive_sha256': digest((source / archive_name).read_bytes()),
             'notebook_sha256': digest((source / 'Untitled3 (1).ipynb').read_bytes())}
    (destination / 'memory_benchmark_audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    main()
