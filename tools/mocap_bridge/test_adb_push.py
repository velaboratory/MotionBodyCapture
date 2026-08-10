"""Unit tests for adb_push.py, mocking subprocess.run -- no real device needed."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from adb_push import AdbPushError, push_file, push_files


def _completed(returncode: int, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


class TestPushFile(unittest.TestCase):
    def test_push_file_success_runs_mkdir_then_push(self):
        with patch("adb_push.subprocess.run", return_value=_completed(0)) as mock_run:
            push_file(Path("/local/track_1.glb"), adb_path="adb", serial=None)

        self.assertEqual(mock_run.call_count, 2)
        mkdir_cmd, push_cmd = (call.args[0] for call in mock_run.call_args_list)
        self.assertEqual(mkdir_cmd[:3], ["adb", "shell", "mkdir"])
        self.assertIn(
            "/sdcard/Android/data/com.samusynth.OpenQuestCapture/files/mocap_playback",
            mkdir_cmd,
        )
        self.assertEqual(push_cmd[0], "adb")
        self.assertEqual(push_cmd[1], "push")
        self.assertTrue(push_cmd[3].endswith("mocap_playback/track_1.glb"))

    def test_push_file_includes_serial_when_given(self):
        with patch("adb_push.subprocess.run", return_value=_completed(0)) as mock_run:
            push_file(Path("/local/track_1.glb"), serial="ABC123")

        for call in mock_run.call_args_list:
            cmd = call.args[0]
            self.assertEqual(cmd[1:3], ["-s", "ABC123"])

    def test_mkdir_failure_raises_before_push(self):
        with patch("adb_push.subprocess.run", return_value=_completed(1, "no devices/emulators found")) as mock_run:
            with self.assertRaises(AdbPushError):
                push_file(Path("/local/track_1.glb"))
        self.assertEqual(mock_run.call_count, 1)  # never got to the push call

    def test_push_failure_after_successful_mkdir_raises(self):
        with patch("adb_push.subprocess.run", side_effect=[_completed(0), _completed(1, "device offline")]):
            with self.assertRaises(AdbPushError):
                push_file(Path("/local/track_1.glb"))

    def test_missing_adb_executable_raises_adb_push_error(self):
        with patch("adb_push.subprocess.run", side_effect=FileNotFoundError()):
            with self.assertRaises(AdbPushError):
                push_file(Path("/local/track_1.glb"))


class TestPushFiles(unittest.TestCase):
    def test_all_succeed_returns_no_warnings(self):
        with patch("adb_push.subprocess.run", return_value=_completed(0)):
            warnings = push_files([Path("/local/track_1.glb"), Path("/local/track_2.glb")])
        self.assertEqual(warnings, [])

    def test_one_failure_does_not_stop_the_rest(self):
        # track_1's mkdir+push succeed (2 calls), track_2's mkdir fails (1 call)
        with patch(
            "adb_push.subprocess.run",
            side_effect=[_completed(0), _completed(0), _completed(1, "offline")],
        ) as mock_run:
            warnings = push_files([Path("/local/track_1.glb"), Path("/local/track_2.glb")])

        self.assertEqual(mock_run.call_count, 3)
        self.assertEqual(len(warnings), 1)
        self.assertIn("track_2.glb", warnings[0])


if __name__ == "__main__":
    unittest.main()
