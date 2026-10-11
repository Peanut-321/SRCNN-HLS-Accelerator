"""Offline tests for deployment packaging gates."""
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from package_aero_delivery import notebook, validate_gate, validate_xsa, delivery_hashes, validate_hwh, validate_constraints, validate_reset_sim
from aero_board_test import validate_reset_tieoffs


class PackageTests(unittest.TestCase):
    def test_reset_simulation_gate_requires_executed_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            log = directory / 'reset_simulation.log'
            log.write_text('# RESET_TIEOFF_PASS: aux=0 holds AXI reset; aux=1 releases AXI reset\n')
            with self.assertRaisesRegex(ValueError, 'executed'):
                validate_reset_sim(directory)
            log.write_text('RESET_TIEOFF_PASS: aux=0 holds AXI reset; aux=1 releases AXI reset\n')
            validate_reset_sim(directory)
            log.write_text(log.read_text() + 'ERROR: simulation failed\n')
            with self.assertRaisesRegex(ValueError, 'error'):
                validate_reset_sim(directory)

    def test_reset_tieoffs_and_wrong_polarity(self):
        root = ET.fromstring('''<MODULES>
          <MODULE INSTANCE="reset"><PARAMETERS>
            <PARAMETER NAME="C_EXT_RESET_HIGH" VALUE="0"/>
            <PARAMETER NAME="C_AUX_RESET_HIGH" VALUE="0"/>
          </PARAMETERS><PORTS>
            <PORT NAME="aux_reset_in"><CONNECTIONS><CONNECTION INSTANCE="one" PORT="dout"/></CONNECTIONS></PORT>
            <PORT NAME="dcm_locked"><CONNECTIONS><CONNECTION INSTANCE="one" PORT="dout"/></CONNECTIONS></PORT>
            <PORT NAME="mb_debug_sys_rst"><CONNECTIONS><CONNECTION INSTANCE="zero" PORT="dout"/></CONNECTIONS></PORT>
          </PORTS></MODULE>
          <MODULE INSTANCE="one" MODTYPE="xlconstant"><PARAMETERS><PARAMETER NAME="CONST_VAL" VALUE="0x1"/></PARAMETERS></MODULE>
          <MODULE INSTANCE="zero" MODTYPE="xlconstant"><PARAMETERS><PARAMETER NAME="CONST_VAL" VALUE="0x0"/></PARAMETERS></MODULE>
        </MODULES>''')
        modules = {m.get('INSTANCE'): m for m in root}
        validate_reset_tieoffs(modules)
        connection = modules['reset'].find("PORTS/PORT[@NAME='aux_reset_in']/CONNECTIONS/CONNECTION")
        connection.set('INSTANCE', 'zero')
        with self.assertRaisesRegex(ValueError, 'Unsafe reset tie-off: aux_reset_in'):
            validate_reset_tieoffs(modules)
        connection.set('INSTANCE', 'one')
        modules['reset'].find("PARAMETERS/PARAMETER[@NAME='C_AUX_RESET_HIGH']").set('VALUE', '1')
        with self.assertRaisesRegex(ValueError, 'reset polarity'):
            validate_reset_tieoffs(modules)

    def test_v2_physical_builds_are_rejected_for_asserted_reset(self):
        paths = [Path(f'C:/fpga/aero-{p}-hpc0-delivery/srcnn_axis_255x255.hwh')
                 for p in ('q248', 'q2012')]
        if not all(p.exists() for p in paths):
            self.skipTest('Local v2 builds are not installed')
        for path in paths:
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, 'Unsafe reset tie-off: aux_reset_in'):
                    validate_hwh(path)

    def test_unconstrained_paths_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            checks = ('no_clock', 'unconstrained_internal_endpoints', 'multiple_clock',
                      'generated_clocks', 'loops', 'latch_loops')
            text = '\n'.join(f'checking {check} (0)' for check in checks)
            (directory / 'check_timing.rpt').write_text(text)
            validate_constraints(directory)
            (directory / 'check_timing.rpt').write_text(text.replace('no_clock (0)', 'no_clock (1)'))
            with self.assertRaisesRegex(ValueError, 'coverage'):
                validate_constraints(directory)

    def test_mutable_notebook_does_not_change_protected_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / 'SRCNN_board_test.ipynb').write_text('original')
            (directory / 'aero_board_test.py').write_text('trusted code')
            before = delivery_hashes(directory)
            (directory / 'SRCNN_board_test.ipynb').write_text('saved outputs')
            self.assertEqual(before, delivery_hashes(directory))
            (directory / 'aero_board_test.py').write_text('modified code')
            self.assertNotEqual(before, delivery_hashes(directory))

    def test_previous_hpm0_delivery_is_rejected(self):
        path = Path('C:/fpga/aero-q248-delivery/srcnn_axis_255x255.hwh')
        if not path.exists():
            self.skipTest('Local previous build is not installed')
        with self.assertRaisesRegex(ValueError, 'Hardware parameter mismatch'):
            validate_hwh(path)

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
