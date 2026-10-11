"""Offline orchestration tests; these do not validate physical hardware."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pynq"))
import aero_board_test as board


class FakeRunner:
    instances = []
    fail = False

    def __init__(self, bit, timeout):
        self.quarantined = []
        self.inputs = []
        self.__class__.instances.append(self)

    def run(self, arrays):
        if self.fail:
            self.quarantined = [object()]
            raise RuntimeError("PL reset failed")
        self.inputs.append(arrays["input"][0])
        return {"status": "PASS", "words": 65025, "transfer_start_to_done_s": 1}, arrays["expected"]


class BoardTests(unittest.TestCase):
    def setUp(self):
        FakeRunner.instances = []
        FakeRunner.fail = False
        board.ACTIVE_RUNNERS.clear()

    def verified(self):
        cases = {name: ({}, {"input": np.array([value]), "expected": np.array([value])})
                 for name, value in (("butterfly", 1), ("changed", 2))}
        return Path("."), {"profile": "q20_12", "source_commit": board.CHECKPOINTS["q20_12"]}, SimpleNamespace(Runner=FakeRunner), cases

    def test_schedule_and_reload(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(board, "verify_delivery", return_value=self.verified()):
            report = board.run_board(".", Path(temp) / "result", iterations=3)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(FakeRunner.instances[0].inputs, [1, 1, 1, 1, 2, 1])
            self.assertEqual(FakeRunner.instances[1].inputs, [1])
            self.assertEqual(report["benchmark"]["measured_frames"], 3)
            self.assertEqual(board.ACTIVE_RUNNERS, [])
            self.assertTrue((Path(temp) / "result" / "board_results.json").is_file())

    def test_failure_retains_runner_and_logs(self):
        FakeRunner.fail = True
        with tempfile.TemporaryDirectory() as temp, patch.object(board, "verify_delivery", return_value=self.verified()):
            out = Path(temp) / "result"
            with self.assertRaises(RuntimeError):
                board.run_board(".", out)
            report = json.loads((out / "board_results.json").read_text())
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["buffers_retained"], 1)
            self.assertEqual(len(board.ACTIVE_RUNNERS), 1)

    def test_invalid_arguments_do_not_program(self):
        with self.assertRaises(ValueError):
            board.run_board(".", "unused", timeout=float("nan"))
        self.assertEqual(FakeRunner.instances, [])

    def test_unapproved_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "delivery_manifest.json").write_text('{}')
            with self.assertRaisesRegex(ValueError, "provenance"):
                board.verify_delivery(directory)


if __name__ == "__main__":
    unittest.main()
