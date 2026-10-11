"""Exercise the delivered host code with fake PYNQ, never physical hardware.

The fake device supplies existing Golden output; this checks host control and
failure handling, not SRCNN arithmetic, AXI RTL, throughput or board performance.
Run separately for each extracted delivery to keep Python module provenance.
"""
import argparse
import contextlib
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--delivery', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
DELIVERY = args.delivery.resolve()


class Buffer(np.ndarray):
    def __new__(cls, state, shape, dtype):
        obj = np.zeros(shape, dtype=dtype).view(cls)
        obj.state, obj.flushed, obj.freed = state, False, False
        obj.physical_address = 0x120000000 + len(state.buffers) * 0x100000
        state.buffers.append(obj)
        state.events.append(('allocate', obj.physical_address))
        return obj

    def flush(self):
        self.flushed = True
        self.state.events.append(('flush', self.physical_address))

    def invalidate(self):
        assert self.state.completed, 'CPU invalidated before DMA completion'
        self.state.events.append(('invalidate', self.physical_address))

    def freebuffer(self):
        assert self.state.completed or self.state.reset_verified, 'Unsafe early free'
        assert not self.freed, 'Double free'
        self.freed = True
        self.state.events.append(('free', self.physical_address))


class Device:
    def __init__(self, cases, behavior='normal', reset_fails=False):
        self.cases, self.behavior, self.reset_fails = cases, behavior, reset_fails
        self.buffers, self.events, self.frames = [], [], []
        self.completed, self.reset_verified = False, True
        self.regs, self.pointer, self.control = {4: 1, 0x34: 1}, {}, 4
        self.started, self.polls, self.overlays = False, 0, 0
        self.dma = SimpleNamespace(read=self.read_dma, write=self.write_dma)
        self.kernel = SimpleNamespace(read=self.read_kernel, write=self.write_kernel)

    def overlay(self, bit, download=True):
        self.overlays += 1
        self.events.append(('overlay',))
        parameters = {'C_INCLUDE_SG': 0, 'C_SG_LENGTH_WIDTH': 26,
                      'C_M_AXIS_MM2S_TDATA_WIDTH': 32, 'C_S_AXIS_S2MM_TDATA_WIDTH': 32}
        return SimpleNamespace(ip_dict={'dma': {'type': 'axi_dma', 'parameters': parameters},
                                        'srcnn': {'type': 'srcnn_axis_dataflow_top'}},
                               dma=SimpleNamespace(mmio=self.dma),
                               srcnn=SimpleNamespace(mmio=self.kernel), download=self.reload)

    def reload(self):
        self.events.append(('recovery_reload',))
        if self.reset_fails:
            raise RuntimeError('injected overlay reset failure')
        self.regs[4] = self.regs[0x34] = 1
        self.control, self.reset_verified, self.started = 4, True, False

    def read_dma(self, offset):
        if offset == 4 and self.started and self.behavior == 'normal':
            self.polls += 1
            if self.polls >= 2:
                self.regs[4] = self.regs[0x34] = 2
                self.completed = True
        return self.regs.get(offset, 0)

    def write_dma(self, offset, value):
        self.events.append(('dma_write', offset, value))
        if offset == 0 and value == 4:
            self.regs = {4: 1, 0x34: 1}
            self.started, self.completed, self.polls = False, False, 0
            return
        self.regs[offset] = value
        if offset in (0, 0x30) and value == 1:
            self.regs[offset + 4] = 0
        if offset == 0x28:
            assert self.started, 'TX armed before kernel start'
            assert all(b.flushed for b in self.buffers[-3:]), 'Unflushed buffer'
            source, destination, model = self.buffers[-3:]
            assert self.regs[0x18] | (self.regs[0x1c] << 32) == source.physical_address
            assert self.regs[0x48] | (self.regs[0x4c] << 32) == destination.physical_address
            assert self.pointer[0x10] | (self.pointer[0x14] << 32) == model.physical_address
            assert value == 65025 * 4 and self.regs[0x58] == value
            matches = [name for name, (_, arrays) in self.cases.items()
                       if np.array_equal(source, arrays['input']) and np.array_equal(model, arrays['model'])]
            assert len(matches) == 1, 'Wrong input/model upload or model failed to switch'
            self.frames.append(matches[0])
            destination[:] = self.cases[matches[0]][1]['expected']
            if self.behavior == 'mismatch':
                destination[127] ^= np.uint32(1)
                self.regs[4] = self.regs[0x34] = 2
                self.completed = True
            elif self.behavior == 'dma_error':
                self.regs[0x34] = 0x20

    def read_kernel(self, offset):
        if offset:
            return self.pointer.get(offset, 0)
        if self.started and self.behavior in ('normal', 'mismatch'):
            # ap_done is clear-on-read and precedes DMA idle by one poll.
            value = self.control
            self.control &= ~2
            return value
        return self.control

    def write_kernel(self, offset, value):
        self.events.append(('kernel_write', offset, value))
        if offset == 0:
            assert self.regs.get(0x58) == 65025 * 4, 'RX must be armed before start'
            self.started, self.reset_verified = True, False
            self.control = 6 if self.behavior in ('normal', 'mismatch') else 0
        else:
            self.pointer[offset] = value

    def module(self):
        return SimpleNamespace(Overlay=self.overlay,
                               allocate=lambda shape, dtype: Buffer(self, shape, dtype),
                               Clocks=SimpleNamespace(fclk0_mhz=199.998001))


class RunnerAudit(unittest.TestCase):
    def setUp(self):
        for name in ('srcnn_axis_host', 'srcnn_q20_12_bundle'):
            sys.modules.pop(name, None)
        spec = importlib.util.spec_from_file_location('audit_board', DELIVERY / 'aero_board_test.py')
        self.board = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.board)
        with contextlib.redirect_stdout(io.StringIO()):
            _, self.manifest, self.host, self.cases = self.board.verify_delivery(DELIVERY)

    def make_runner(self, device):
        with patch.dict(sys.modules, {'pynq': device.module()}):
            return self.host.Runner(DELIVERY / 'srcnn_axis_255x255.bit', timeout=2.0)

    def test_real_runner_switch_restore_without_pl_reload(self):
        dev = Device(self.cases)
        runner = self.make_runner(dev)
        for case in ('butterfly', 'changed', 'butterfly'):
            result, output = runner.run(self.cases[case][1])
            self.assertTrue(result['exact_match'])
            np.testing.assert_array_equal(output, self.cases[case][1]['expected'])
        self.assertEqual(dev.frames, ['butterfly', 'changed', 'butterfly'])
        self.assertEqual(dev.overlays, 1)
        self.assertNotIn(('recovery_reload',), dev.events)
        self.assertTrue(all(b.freed for b in dev.buffers))
        self.assertEqual(len([e for e in dev.events if e[0] == 'invalidate']), 3)

    def test_real_aero_schedule_and_reload(self):
        dev = Device(self.cases)
        with tempfile.TemporaryDirectory() as temp, patch.dict(sys.modules, {'pynq': dev.module()}), contextlib.redirect_stdout(io.StringIO()):
            report = self.board.run_board(DELIVERY, Path(temp) / 'result', iterations=3, timeout=2.0)
            self.assertEqual(report['status'], 'PASS')
            self.assertTrue(report['not_kernel_only'])
            self.assertEqual(report['benchmark']['measured_frames'], 3)
            self.assertEqual(dev.frames, ['butterfly'] * 4 + ['changed', 'butterfly', 'butterfly'])
            self.assertEqual(dev.overlays, 2)
            self.assertEqual(self.board.ACTIVE_RUNNERS, [])
            self.assertTrue(all(b.freed for b in dev.buffers))
            self.assertEqual(len(list((Path(temp) / 'result').glob('output*.npy'))), 7)

    def test_dma_error_resets_whole_pl_before_free(self):
        dev = Device(self.cases, 'dma_error')
        runner = self.make_runner(dev)
        with self.assertRaisesRegex(RuntimeError, 'DMA error'):
            runner.run(self.cases['butterfly'][1])
        reset = dev.events.index(('recovery_reload',))
        self.assertTrue(all(i > reset for i, e in enumerate(dev.events) if e[0] == 'free'))
        self.assertTrue(all(b.freed for b in dev.buffers))
        self.assertEqual(runner.quarantined, [])

    def test_timeout_is_bounded_and_releases_after_verified_reset(self):
        dev = Device(self.cases, 'timeout')
        runner = self.make_runner(dev)
        original = self.host.wait_complete
        ticks = iter((0, 3))
        with patch.object(self.host, 'wait_complete',
                          side_effect=lambda d, k, t: original(d, k, t, clock=lambda: next(ticks), pause=lambda _: None)):
            with self.assertRaisesRegex(TimeoutError, 'completion timeout'):
                runner.run(self.cases['butterfly'][1])
        self.assertIn(('recovery_reload',), dev.events)
        self.assertTrue(all(b.freed for b in dev.buffers))

    def test_failed_reset_retains_buffers_and_blocks_retry(self):
        dev = Device(self.cases, 'dma_error', reset_fails=True)
        runner = self.make_runner(dev)
        with self.assertRaisesRegex(RuntimeError, 'buffers retained'):
            runner.run(self.cases['butterfly'][1])
        self.assertEqual(len(runner.quarantined), 3)
        self.assertTrue(all(not b.freed for b in dev.buffers))
        before = list(dev.events)
        with self.assertRaisesRegex(RuntimeError, 'previous transfer failed'):
            runner.run(self.cases['butterfly'][1])
        self.assertEqual(dev.events, before)

    def test_reload_without_quiescent_registers_retains_buffers(self):
        dev = Device(self.cases, 'dma_error')
        runner = self.make_runner(dev)
        runner.overlay.download = lambda: None
        with self.assertRaisesRegex(RuntimeError, 'buffers retained'):
            runner.run(self.cases['butterfly'][1])
        self.assertEqual(len(runner.quarantined), 3)
        self.assertTrue(all(not b.freed for b in dev.buffers))

    def test_dma_byte_count_mismatch_rejected(self):
        dev = Device(self.cases)
        runner = self.make_runner(dev)
        original_read = dev.read_dma
        runner.dma.read = lambda offset: 260096 if offset == 0x58 else original_read(offset)
        with self.assertRaisesRegex(RuntimeError, 'byte count mismatch'):
            runner.run(self.cases['butterfly'][1])
        self.assertTrue(all(b.freed for b in dev.buffers))

    def test_dma_reset_timeout_is_bounded(self):
        ticks = iter((0, 3))
        stuck = SimpleNamespace(read=lambda offset: 4, write=lambda offset, value: None)
        with patch.object(self.host.time, 'monotonic', side_effect=lambda: next(ticks)):
            with self.assertRaisesRegex(TimeoutError, 'DMA reset timeout'):
                self.host.reset_dma(stuck)

    def test_wrapper_keeps_failed_runner_alive_and_writes_failure(self):
        dev = Device(self.cases, 'dma_error', reset_fails=True)
        with tempfile.TemporaryDirectory() as temp, patch.dict(sys.modules, {'pynq': dev.module()}), contextlib.redirect_stdout(io.StringIO()):
            out = Path(temp) / 'result'
            with self.assertRaisesRegex(RuntimeError, 'buffers retained'):
                self.board.run_board(DELIVERY, out, timeout=2.0)
            report = json.loads((out / 'board_results.json').read_text())
            self.assertEqual(report['status'], 'FAIL')
            self.assertEqual(report['buffers_retained'], 3)
            self.assertEqual(len(self.board.ACTIVE_RUNNERS), 1)
            self.assertTrue(all(not b.freed for b in dev.buffers))

    def test_wrong_output_never_passes_and_frees_completed_buffers(self):
        dev = Device(self.cases, 'mismatch')
        runner = self.make_runner(dev)
        with self.assertRaisesRegex(AssertionError, 'first pixel 127'):
            runner.run(self.cases['butterfly'][1])
        self.assertNotIn(('recovery_reload',), dev.events)
        self.assertTrue(all(b.freed for b in dev.buffers))

    def test_bad_bit_rejected_before_overlay_creation(self):
        dev = Device(self.cases)
        with patch.object(self.host, 'BIT_SHA256', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'hashes differ'):
                self.make_runner(dev)
        self.assertEqual(dev.overlays, 0)

    def test_bad_bundle_checksum_rejected(self):
        reader = self.host.read_bundle if self.manifest['profile'] == 'q24_8' else sys.modules['srcnn_q20_12_bundle'].read_bundle
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / 'bundle'
            shutil.copytree(DELIVERY / 'butterfly', dest)
            path = dest / 'model.npy'
            data = bytearray(path.read_bytes())
            data[-1] ^= 1
            path.write_bytes(data)
            with self.assertRaises(ValueError):
                reader(dest)

    def test_other_profile_contract_rejected(self):
        reader = self.host.read_bundle if self.manifest['profile'] == 'q24_8' else sys.modules['srcnn_q20_12_bundle'].read_bundle
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / 'bundle'
            shutil.copytree(DELIVERY / 'butterfly', dest)
            path = dest / 'manifest.json'
            manifest = json.loads(path.read_text())
            manifest['format'] = 'signed Q20.12 raw bits in uint32' if self.manifest['profile'] == 'q24_8' else 'signed Q24.8 raw bits in uint32'
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                reader(dest)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RunnerAudit)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    proof = {'audit_kind': 'OFFLINE_FAKE_PYNQ_ONLY', 'board_tested': False,
             'arithmetic_tested': False, 'profile': json.loads((DELIVERY / 'delivery_manifest.json').read_text())['profile'],
             'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
             'passed': result.wasSuccessful(), 'audit_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    proof['delivery_manifest_sha256'] = hashlib.sha256((DELIVERY / 'delivery_manifest.json').read_bytes()).hexdigest()
    proof['delivered_scripts_sha256'] = {name: hashlib.sha256((DELIVERY / name).read_bytes()).hexdigest()
                                        for name in ('srcnn_axis_host.py', 'aero_board_test.py')}
    args.out.write_text(json.dumps(proof, indent=2) + '\n')
    sys.exit(not result.wasSuccessful())
