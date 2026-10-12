"""Audit canonical evidence and generate safe English reproduction notebooks."""
import hashlib
import ast
import io
import json
import shutil
import statistics
import tempfile
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_notebook(path, cells):
    prepared = []
    for i, (kind, text) in enumerate(cells):
        cell = {'cell_type': kind, 'id': f'cell-{i}', 'metadata': {}, 'source': text.splitlines(keepends=True)}
        assert text.isascii(), 'Reproduction content must be English/ASCII'
        if kind == 'code':
            compile(text, str(path), 'exec')
            cell.update(execution_count=None, outputs=[])
        prepared.append(cell)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'nbformat': 4, 'nbformat_minor': 5,
        'metadata': {'kernelspec': {'display_name': 'Python 3 (ipykernel)', 'language': 'python', 'name': 'python3'}},
        'cells': prepared}, indent=2), encoding='utf-8', newline='\n')


def main():
    audit = {'status': 'PASS', 'date': '2026-10-12', 'formats': {}}
    for profile in ('q20_12', 'q24_8'):
        package = ROOT / 'deliverables/aero-local' / f'srcnn_{profile}_v3_resetfix.zip'
        prefix = f'srcnn_{profile}_v3_resetfix/'
        with zipfile.ZipFile(package) as z:
            assert z.testzip() is None
            manifest = json.loads(z.read(prefix + 'delivery_manifest.json'))
            assert manifest['profile'] == profile
            assert manifest['deployment_revision'] == 'HPM1_HPC0_B000_B001_RESETFIX_V3'
            for name, expected in manifest['files'].items():
                assert sha(z.read(prefix + name)) == expected, name
            for case in ('butterfly', 'changed'):
                bundle = json.loads(z.read(prefix + case + '/manifest.json'))
                for name, item in bundle['artifacts'].items():
                    assert sha(z.read(prefix + case + '/' + name)) == item['sha256']
            expected_original = np.load(io.BytesIO(z.read(prefix + 'butterfly/expected.npy')), allow_pickle=False)
            expected_changed = np.load(io.BytesIO(z.read(prefix + 'changed/expected.npy')), allow_pickle=False)
            with zipfile.ZipFile(ROOT / 'results/srcnn-board' / profile / (profile + '_board_results.zip')) as result:
                assert result.testzip() is None
                report = json.loads(result.read(next(n for n in result.namelist() if n.endswith('board_results.json'))))
                assert report['status'] == 'PASS' and len(report['runs']) == 14
                assert [r['phase'] for r in report['runs']] == ['warmup'] + ['repeat'] * 10 + ['changed', 'restored', 'reload']
                outputs = [n for n in result.namelist() if n.endswith('.npy')]
                assert len(outputs) == 14
                for name in outputs:
                    actual = np.load(io.BytesIO(result.read(name)), allow_pickle=False)
                    expected = expected_changed if 'changed' in name else expected_original
                    assert actual.dtype == expected.dtype and actual.shape == expected.shape
                    assert np.array_equal(actual, expected)
                for run in report['runs']:
                    assert run['exact_match'] and run['words'] == 65025
                    assert run['identity']['bit_sha256'] == manifest['files']['srcnn_axis_255x255.bit']
                    assert run['identity']['hwh_sha256'] == manifest['files']['srcnn_axis_255x255.hwh']
                median = statistics.median(r['transfer_start_to_done_s'] for r in report['runs'] if r['phase'] == 'repeat')
            clean = json.loads(z.read(prefix + 'SRCNN_board_test.ipynb'))
            cells = [(c['cell_type'], ''.join(c['source'])) for c in clean['cells']]
            cells.insert(0, ('markdown', '# Final V3 English reproduction notebook\n\nCopy this notebook into the extracted delivery directory before opening it. Requires KV260 PYNQ, Python 3.10+ and NumPy. Run one format/kernel at a time. Hardware switches default to False. This clean copy has not been physically re-executed; the original executed notebook is preserved under results/srcnn-board.\n\nThe deployment ZIP was frozen before physical validation, so its historical PENDING text is superseded by the audited evidence. Never edit hashed runtime files or mix BIT/HWH/model formats.\n'))
            cells.append(('code', 'import shutil\n\n# Archive results only after a successful run.\nif RUN_BOARD and report["status"] == "PASS":\n    archive = shutil.make_archive(str(output_dir), "zip", root_dir=str(output_dir))\n    print("Download results archive:", archive)\n'))
            notebook_path = ROOT / 'deliverables/aero-local/SRCNN_V3_Run_EN.ipynb'
            write_notebook(notebook_path, cells)
            for kind, text in cells:
                if kind == 'code':
                    for node in ast.walk(ast.parse(text)):
                        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ('RUN_BOARD', 'RUN_PREFLIGHT') for t in node.targets):
                            assert isinstance(node.value, ast.Constant) and node.value.value is False
            audit['formats'][profile] = {'deployment_archive_sha256': sha(package.read_bytes()),
                'verified_manifest_files': len(manifest['files']), 'original_board_frames': 14,
                'exact_output_words': 14 * 65025, 'median_transfer_seconds': median,
                'english_notebook_sha256': sha(notebook_path.read_bytes()), 'source_commit': manifest['source_commit']}
    kit_source = ROOT / '.codex-build/q20_12_return_board_check'
    archive = ROOT / 'deliverables/aero-local/q20_12_return_board_check_EN.zip'
    with tempfile.TemporaryDirectory(prefix='srcnn-english-', dir=ROOT / '.codex-build') as tmp:
        kit = Path(tmp) / 'q20_12_return_board_check'
        kit.mkdir()
        shutil.copytree(kit_source / 'cases', kit / 'cases')
        shutil.copyfile(kit_source / 'offline_metrics.json', kit / 'offline_metrics.json')
        for name in ('deployment_numeric.py', 'precision_numeric.py', 'srcnn_q20_12_bundle.py',
                     'supplement_board.py', 'cpu_reference.cpp', 'benchmark_memory_to_memory.py'):
            shutil.copyfile(Path(__file__).with_name(name), kit / name)
        cells = [('markdown', '# Q20.12 supplementary validation and benchmark\n\nExtract this English kit in the board Project directory next to srcnn_q20_12_v3_resetfix. Do not overwrite an existing kit: retain its results and use the original executed record, or deliberately move the old kit before extraction. Python 3.10+, NumPy, PYNQ and g++ are required. No hardware action occurs on import. This is an unexecuted reproduction copy; keep original logs unchanged.\n\nThe CPU test uses Butterfly, scalar single-thread C++ GCC -O3. The FPGA image test uses the 14 supplied images. The final benchmark compares functional memory-to-memory boundaries, not isolated kernel timing or an optimized CPU library.\n'),
            ('code', 'from pathlib import Path\nimport sys\n\nkit = Path.cwd().resolve()\nsys.path.insert(0, str(kit))\nimport supplement_board\nsupplement_board.check_kit(kit)\nproject = kit.parent\nprint("Kit verified. No FPGA programming in this cell.")\n'),
            ('code', 'RUN_IMAGES = False\nif RUN_IMAGES:\n    import shutil\n    output_dir = supplement_board.run_images(project / "srcnn_q20_12_v3_resetfix", kit)\n    print("Results archive:", shutil.make_archive(str(output_dir), "zip", root_dir=str(output_dir)))\n'),
            ('code', 'RUN_CPU = False\nif RUN_CPU:\n    import shutil\n    cpu_output_dir = supplement_board.run_cpu(kit, case="butterfly", repeats=3)\n    print("CPU results archive:", shutil.make_archive(str(cpu_output_dir), "zip", root_dir=str(cpu_output_dir)))\n'),
            ('code', 'RUN_BENCHMARK = False\nif RUN_BENCHMARK:\n    import benchmark_memory_to_memory\n    # Reuse the CPU record generated above, not a historical fixed timestamp.\n    benchmark_output_dir = benchmark_memory_to_memory.run(project, cpu_directory=cpu_output_dir)\n')]
        write_notebook(kit / 'Q20_12_Supplementary_Run_EN.ipynb', cells)
        hashes = {p.relative_to(kit).as_posix(): sha(p.read_bytes()) for p in sorted(kit.rglob('*')) if p.is_file()}
        (kit / 'kit_checksums.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(kit.rglob('*')):
                if p.is_file():
                    z.write(p, p.relative_to(Path(tmp)).as_posix())
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            assert not any('\\' in name for name in z.namelist())
        audit['english_supplementary_kit'] = {'sha256': sha(archive.read_bytes()), 'files_checked': len(hashes),
            'status': 'Offline validated reproduction package; not physically re-executed'}
    (ROOT / 'results/srcnn-board/final_english_delivery_audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    main()
