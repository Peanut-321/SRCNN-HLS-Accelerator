"""Corrected runtime initialization tests use no physical hardware."""
import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pynq'))
import aero_srcnn_axis_host as host


class RuntimeTests(unittest.TestCase):
    def test_direct_mmio_without_dma_driver(self):
        events = []
        class Overlay:
            def __init__(self, path, download):
                self.device = object()
                self.ip_dict = {
                    'dma': {'type': 'xilinx.com:ip:axi_dma:7.1', 'phys_addr': 0xB0000000,
                            'addr_range': 65536, 'parameters': {
                                'C_INCLUDE_SG': 0, 'C_SG_LENGTH_WIDTH': 26,
                                'C_M_AXIS_MM2S_TDATA_WIDTH': 32, 'C_S_AXIS_S2MM_TDATA_WIDTH': 32}},
                    'srcnn': {'type': 'xilinx.com:hls:srcnn_axis_dataflow_top:1.0',
                              'phys_addr': 0xB0010000, 'addr_range': 65536}}
                assert download is False
            def download(self):
                events.append('download')
            @property
            def dma(self):
                raise AssertionError('Unused DMA driver must not be constructed')
        def mmio(address, length, device):
            events.append(address)
            return SimpleNamespace(address=address)
        fake = SimpleNamespace(Overlay=Overlay, MMIO=mmio, allocate=lambda **kw: None,
                               Clocks=SimpleNamespace(fclk0_mhz=200))
        with tempfile.TemporaryDirectory() as temp:
            bit = Path(temp) / 'test.bit'
            bit.write_bytes(b'bit')
            bit.with_suffix('.hwh').write_bytes(b'hwh')
            with patch.dict(sys.modules, {'pynq': fake}), \
                    patch.object(host, 'BIT_SHA256', hashlib.sha256(b'bit').hexdigest()), \
                    patch.object(host, 'HWH_SHA256', hashlib.sha256(b'hwh').hexdigest()):
                runner = host.Runner(bit)
                self.assertEqual(events, ['download', 0xB0000000, 0xB0010000])
                self.assertEqual(runner.kernel.address, 0xB0010000)
                bit.with_suffix('.xsa').write_bytes(b'archive')
                with self.assertRaisesRegex(ValueError, 'sibling XSA'):
                    host.Runner(bit)


if __name__ == '__main__':
    unittest.main()
