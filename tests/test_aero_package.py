"""Offline tests for deployment packaging gates."""
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from package_aero_delivery import notebook, validate_gate, validate_xsa


class PackageTests(unittest.TestCase):
    def test_xsa_requires_matching_pair(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "srcnn_axis_255x255.bit").write_bytes(b'bit')
            (directory / "srcnn_axis_255x255.hwh").write_bytes(b'hwh')
            archive_path = directory / "srcnn_axis_255x255.xsa"
            with zipfile.ZipFile(archive_path, 'w') as archive:
                archive.writestr('system.bit', b'bit')
                archive.writestr('system.hwh', b'hwh')
            validate_xsa(directory)
            (directory / "srcnn_axis_255x255.bit").write_bytes(b'wrong-build')
            with self.assertRaisesRegex(ValueError, "standalone"):
                validate_xsa(directory)

    def test_tcl_echo_is_not_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "console-all.log").write_text('# puts "GATE_BITSTREAM_PASS"\n')
            with self.assertRaisesRegex(ValueError, "completed"):
                validate_gate(directory)

    def test_negative_timing_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "console-all.log").write_text('GATE_BITSTREAM_PASS\n')
            (directory / "implementation_gate.txt").write_text('WNS -0.01\nWHS 0.01\nDRC_BLOCKERS 0\n')
            with self.assertRaisesRegex(ValueError, "Timing"):
                validate_gate(directory)

    def test_valid_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "console-all.log").write_text('GATE_BITSTREAM_PASS\n')
            (directory / "implementation_gate.txt").write_text('WNS 0.07\nWHS 0.01\nDRC_BLOCKERS 0\n')
            self.assertEqual(validate_gate(directory)["WNS"], '0.07')

    def test_notebook_starts_unexecuted(self):
        artifact = notebook()
        cells = [cell for cell in artifact["cells"] if cell["cell_type"] == "code"]
        self.assertTrue(all(cell["execution_count"] is None and cell["outputs"] == [] for cell in cells))
        self.assertIn('RUN_BOARD = False', ''.join(cells[-1]["source"]))
        for cell in cells:
            compile(''.join(cell["source"]), '<notebook-cell>', 'exec')


if __name__ == '__main__':
    unittest.main()
