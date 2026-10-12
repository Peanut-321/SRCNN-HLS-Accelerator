"""Audit downloaded evidence without executing notebook or board code."""
import hashlib
import io
import json
import shutil
import statistics
import zipfile
from pathlib import Path

import numpy as np


def main():
    source = Path('C:/Users/aeroc/Desktop/文件/EE/2026S2/90096/Project')
    kit = Path('.codex-build/q20_12_return_board_check')
    out = Path('results/srcnn-board/q20_12/return-board-2026-10-12')
    out.mkdir(parents=True, exist_ok=True)
    names = ['additional_board_results_20260817T063556_159491Z.zip',
             'cpu_results_20260817T063705_562593Z.zip', 'Untitled3.ipynb']
    offline = json.loads((kit / 'offline_metrics.json').read_text())
    cases = {c['name'] for c in offline['cases']}
    verified = []
    with zipfile.ZipFile(source / names[0]) as board:
        assert board.testzip() is None
        report = json.loads(board.read('board_results.json'))
        assert report['status'] == 'PASS'
        assert len(report['runs']) == 14
        assert {r['case'] for r in report['runs']} == cases
        assert len(board.namelist()) == 15
        for run in report['runs']:
            name = run['case']
            actual = np.load(io.BytesIO(board.read(name + '.npy')), allow_pickle=False)
            expected = np.load(kit / 'cases' / name / 'expected.npy', allow_pickle=False)
            assert actual.dtype == expected.dtype and actual.shape == expected.shape
            assert actual.size == 65025 and np.array_equal(actual, expected)
            assert run['status'] == 'PASS' and run['exact_match'] and run['words'] == 65025
            assert run['identity']['bit_sha256'] == '24914ab05e129866847a9903dbd4fff5942b27f1d0da1b4aea28dc5776f96725'
            assert run['identity']['hwh_sha256'] == '2049f2a5bc5d5c4272e3de540a7ffe5611307bac7b9b5da65ac99d60b675ce77'
            verified.append(name)
    with zipfile.ZipFile(source / names[1]) as cpu:
        assert cpu.testzip() is None
        cpu_report = json.loads(cpu.read('cpu_results.json'))
        assert cpu_report['status'] == 'PASS' and cpu_report['case'] == 'butterfly'
        assert len(cpu_report['runs']) == 4
        expected = np.load(kit / 'cases/butterfly/expected.npy', allow_pickle=False)
        for i, run in enumerate(cpu_report['runs']):
            actual = np.frombuffer(cpu.read(f'output_{i}.bin'), dtype='<u4')
            assert actual.size == 65025 and np.array_equal(actual, expected)
            assert run['exact_match'] and run['phase'] == ('warmup' if i == 0 else 'repeat')
        median = statistics.median(r['compute_seconds'] for r in cpu_report['runs'][1:])
        assert median == cpu_report['median_compute_seconds']
    hashes = {}
    for name in names:
        target = out / name
        data = (source / name).read_bytes()
        if target.exists():
            assert target.read_bytes() == data, 'Refusing to overwrite different evidence'
        else:
            shutil.copyfile(source / name, target)
        hashes[name] = hashlib.sha256(data).hexdigest()
    nb = json.loads((source / names[2]).read_text(encoding='utf-8'))
    assert len(nb['cells']) == 4
    for cell in nb['cells']:
        if cell['cell_type'] == 'code':
            compile(''.join(cell['source']), '<archived-notebook>', 'exec')
    audit = {'status': 'PASS', 'audit_date': '2026-10-12',
             'board_clock_warning': 'Original filenames use an incorrect board clock; not the actual test date.',
             'board_cases': sorted(verified), 'board_exact_words': 14 * 65025,
             'cpu_exact_runs': 4, 'cpu_median_compute_seconds': median,
             'board_median_across_14_distinct_images_seconds': statistics.median(r['transfer_start_to_done_s'] for r in report['runs']),
             'timing_limitation': 'CPU scalar C++ compute-only versus FPGA model-load and DMA window; not an optimized CPU comparison or matched timing boundary.',
             'minimum_fixed_vs_float_agreement_psnr_db': offline['min_fixed_vs_float_psnr_db'],
             'maximum_absolute_reconstruction_psnr_delta_db': offline['max_absolute_reconstruction_psnr_delta_db'],
             'sha256': hashes}
    (out / 'audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    code = '''from pathlib import Path
from zipfile import ZipFile
import hashlib
import json
import shutil
import sys

# Run from the Jupyter Project directory on the KV260.
# These switches are intentionally disabled. This copy has NOT been executed.
RUN_BOARD = False
RUN_CPU = False
kit = Path("q20_12_return_board_check")
if not kit.is_dir():
    with ZipFile("q20_12_return_board_check.zip") as archive:
        for name in archive.namelist():
            resolved = Path(name).resolve()
            if not resolved.is_relative_to(Path.cwd().resolve()):
                raise ValueError("Unsafe archive path: " + name)
        if archive.testzip() is not None:
            raise ValueError("Archive CRC check failed")
        archive.extractall(".")
sys.path.insert(0, str(kit.resolve()))
import supplement_board

def check_kit_cross_platform(path):
    root = Path(path).resolve()
    hashes = json.loads((root / "kit_checksums.json").read_text())
    for name, expected in hashes.items():
        file = (root / name.replace("\\\\", "/")).resolve()
        if not file.is_relative_to(root):
            raise ValueError("Path escapes kit directory: " + name)
        if not file.is_file():
            raise FileNotFoundError("Missing kit file: " + name)
        if hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise ValueError("Checksum mismatch: " + name)
    return root

# Normalize Windows manifest separators while retaining all integrity checks.
supplement_board.check_kit = check_kit_cross_platform
check_kit_cross_platform(kit)
if RUN_BOARD:
    output_dir = supplement_board.run_images(Path("srcnn_q20_12_v3_resetfix"), kit)
    board_zip = shutil.make_archive(str(output_dir), "zip", root_dir=str(output_dir))
    print("Board results archive:", board_zip)
if RUN_CPU:
    cpu_output_dir = supplement_board.run_cpu(kit, case="butterfly", repeats=3)
    cpu_zip = shutil.make_archive(str(cpu_output_dir), "zip", root_dir=str(cpu_output_dir))
    print("CPU results archive:", cpu_zip)
'''
    compile(code, '<english-notebook>', 'exec')
    english = {'nbformat': 4, 'nbformat_minor': 5, 'metadata': nb.get('metadata', {}), 'cells': [
        {'cell_type': 'markdown', 'id': 'scope', 'metadata': {}, 'source': [
            '# Q20.12 V3 supplementary board and CPU tests\n',
            'English-language reproduction copy, not an executed test record. Original Untitled3.ipynb and downloaded ZIPs are preserved unchanged.\n',
            'FPGA: 14 distinct supplied images, exact fixed-point reference comparison. CPU: scalar single-thread C++ compiled with GCC -O3, Butterfly only. Timing boundaries differ.\n',
            'Enable switches only when deliberately repeating tests on the KV260. Do not run concurrent board notebooks.\n']},
        {'cell_type': 'code', 'id': 'explicit-tests', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': code.splitlines(keepends=True)}]}
    (out / 'Q20_12_Supplementary_Tests_EN.ipynb').write_text(json.dumps(english, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(audit, indent=2))
    print('Saved:', out.resolve())


if __name__ == '__main__':
    main()
