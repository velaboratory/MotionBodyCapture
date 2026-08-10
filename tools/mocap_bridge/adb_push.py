"""Push exported .glb files onto a connected Quest headset via adb, into the
folder OpenQuestCapture's Playback tab scans (Assets/RealityLog/Scripts/Runtime/
UI/PlaybackFileManager.cs, playbackDirectoryName = "mocap_playback").

Best-effort by design: callers should treat failures here as warnings, not
hard errors -- the .glb is already saved locally either way, this is a bonus
final step that only works when the headset happens to be on USB.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

DEVICE_PLAYBACK_DIR = "/sdcard/Android/data/com.samusynth.OpenQuestCapture/files/mocap_playback"


class AdbPushError(RuntimeError):
    pass


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise AdbPushError(f"'{cmd[0]}' not found -- is Android platform-tools on PATH?") from e


def push_file(
    local_path: Path,
    adb_path: str = "adb",
    serial: str | None = None,
    device_dir: str = DEVICE_PLAYBACK_DIR,
) -> None:
    """adb-push a single file into the OpenQuestCapture app's playback folder on-device."""
    serial_args = ["-s", serial] if serial else []

    mkdir_result = _run([adb_path, *serial_args, "shell", "mkdir", "-p", device_dir])
    if mkdir_result.returncode != 0:
        raise AdbPushError(f"adb mkdir -p {device_dir} failed: {mkdir_result.stderr.strip()}")

    push_result = _run([adb_path, *serial_args, "push", str(local_path), f"{device_dir}/{local_path.name}"])
    if push_result.returncode != 0:
        raise AdbPushError(f"adb push {local_path.name} failed: {push_result.stderr.strip()}")


def push_files(
    paths: list[Path],
    adb_path: str = "adb",
    serial: str | None = None,
    device_dir: str = DEVICE_PLAYBACK_DIR,
) -> list[str]:
    """Push multiple files. Returns a warning string per file that failed (empty list = all succeeded)."""
    warnings: list[str] = []
    for path in paths:
        try:
            push_file(path, adb_path=adb_path, serial=serial, device_dir=device_dir)
            print(f"[adb_push] Pushed {path.name} -> {device_dir}/")
        except AdbPushError as e:
            warnings.append(f"{path.name}: {e}")
    return warnings
