#!/usr/bin/env python3
"""
Watches a USB-connected Quest headset for finished MotionBodyCapture recording
sessions and automatically runs each one through the Mo=Cat Studio bridge
(tools/mocap_bridge/run.py), so the only manual step is record -> stop on the
headset -- results land back in the Playback tab on their own.

Usage:
    python watch_and_process.py --ssh-host user@backend-host [--ssh-port 22]
                                 [--backend-port 8001] [--camera left]
                                 [--adb-serial SERIAL] [--poll-interval 5]
    (or set OQC_SSH_HOST / OQC_SSH_PORT; use --no-tunnel if the backend is
    already reachable on localhost)

Requires: adb on PATH (or --adb-path), an ssh client on PATH, and this venv's
own deps (requirements.txt) -- separate from run.py's other args, this script
owns the SSH tunnel and session discovery; run.py still does the actual work
per session.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

if sys.platform == "win32":
    # Avoid UnicodeEncodeError from status glyphs (checkmarks etc.) on the
    # default cp1252 Windows console -- bit us twice already in the backend.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
import tempfile
import time
from pathlib import Path

APP_PACKAGE = "com.velaboratory.MotionBodyCapture"
DEVICE_FILES_ROOT = f"/sdcard/Android/data/{APP_PACKAGE}/files"
SESSION_DIR_RE = re.compile(r"^\d{8}_\d{6}$")  # matches RecordingManager's yyyyMMdd_HHmmss
KNOWN_NON_SESSION_DIRS = {"mocap_playback", "Downloads"}
STATE_FILE = Path(__file__).parent / ".watch_state.json"
STABLE_POLLS_REQUIRED = 2  # consecutive unchanged polls before treating a session as finished


def find_adb() -> str:
    """Prefer adb on PATH; otherwise search Unity Hub's bundled Android SDKs
    (newest editor first) since that's where most Quest devs actually have one."""
    on_path = shutil.which("adb")
    if on_path:
        return on_path
    pattern = "C:/Program Files/Unity/Hub/Editor/*/Editor/Data/PlaybackEngines/AndroidPlayer/SDK/platform-tools/adb.exe"
    matches = sorted(glob.glob(pattern), reverse=True)
    if matches:
        return matches[0]
    return "adb"  # fall through to a clear "not found" error at call time


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def adb(adb_path: str, serial: str | None, *args: str) -> subprocess.CompletedProcess:
    cmd = [adb_path]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    return run(cmd)


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"processed": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def list_candidate_sessions(adb_path: str, serial: str | None) -> list[str]:
    result = adb(adb_path, serial, "shell", f"ls -1 {DEVICE_FILES_ROOT}")
    if result.returncode != 0:
        return []
    names = [n.strip() for n in result.stdout.splitlines() if n.strip()]
    return [
        n for n in names
        if n not in KNOWN_NON_SESSION_DIRS and SESSION_DIR_RE.match(n)
    ]


def dir_fingerprint(adb_path: str, serial: str | None, session: str) -> str | None:
    """Cheap stability check: total size + newest mtime under the session dir."""
    remote_dir = f"{DEVICE_FILES_ROOT}/{session}"
    result = adb(
        adb_path, serial, "shell",
        f"du -sb {remote_dir} 2>/dev/null; "
        f"find {remote_dir} -type f -printf '%T@\\n' 2>/dev/null | sort -n | tail -1",
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def pull_session(
    adb_path: str, serial: str | None, session: str, dest_root: Path, camera: str = "left"
) -> Path:
    """Pull a session, skipping the other camera's raw frames.

    The bridge only decodes one camera, and the raw frames are the bulk of the
    data, so pulling both roughly doubles the transfer for nothing.
    """
    remote_dir = f"{DEVICE_FILES_ROOT}/{session}"
    local_dir = dest_root / session
    local_dir.mkdir(parents=True, exist_ok=True)

    listing = adb(adb_path, serial, "shell", f"ls -1 {remote_dir}")
    if listing.returncode != 0:
        raise RuntimeError(f"could not list {session} on the device: {listing.stderr}")
    skip = f"{'right' if camera == 'left' else 'left'}_camera_raw"
    for entry in (e.strip() for e in listing.stdout.splitlines()):
        if not entry or entry == skip:
            continue
        result = adb(adb_path, serial, "pull", f"{remote_dir}/{entry}", str(local_dir))
        if result.returncode != 0:
            raise RuntimeError(f"adb pull failed for {session}/{entry}: {result.stderr}")
    return local_dir


def start_ssh_tunnel(ssh_host: str, ssh_port: int, backend_port: int) -> subprocess.Popen:
    cmd = [
        "ssh", "-N",
        "-p", str(ssh_port),
        "-L", f"{backend_port}:localhost:{backend_port}",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=30",
        ssh_host,
    ]
    print(f"[watch] Opening SSH tunnel: {' '.join(cmd)}", flush=True)
    return subprocess.Popen(cmd)


def wait_for_backend(backend_port: int, timeout: float = 20.0) -> bool:
    import urllib.request
    import urllib.error

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://localhost:{backend_port}/", timeout=2)
            return True
        except urllib.error.HTTPError:
            return True  # any HTTP response (even 404) means the server is up
        except Exception:
            time.sleep(1)
    return False


def process_session(
    session_dir: Path, backend_port: int, camera: str, adb_path: str, serial: str | None,
    use_fp16: bool = False,
) -> bool:
    run_py = Path(__file__).parent / "run.py"
    venv_python = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
    python_exe = str(venv_python) if venv_python.exists() else sys.executable

    cmd = [
        python_exe, str(run_py),
        "--session", str(session_dir),
        "--backend-url", f"http://localhost:{backend_port}",
        "--camera", camera,
        "--adb-path", adb_path,
    ]
    if serial:
        cmd += ["--adb-serial", serial]
    if use_fp16:
        cmd += ["--use-fp16"]

    print(f"[watch] Processing session {session_dir.name} ...", flush=True)
    result = subprocess.run(cmd)
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--ssh-host", default=os.environ.get("OQC_SSH_HOST"),
        help="user@host of the machine running the Mo=Cat backend (env: OQC_SSH_HOST); not needed with --no-tunnel",
    )
    parser.add_argument(
        "--ssh-port", type=int, default=int(os.environ.get("OQC_SSH_PORT", "22")),
        help="SSH port of that machine (env: OQC_SSH_PORT, default 22)",
    )
    parser.add_argument("--backend-port", type=int, default=8001)
    parser.add_argument("--camera", default="left", choices=["left", "right"])
    parser.add_argument("--adb-path", default=None, help="Path to adb (default: PATH, then Unity Hub's bundled SDK)")
    parser.add_argument("--adb-serial", default=None)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--no-tunnel", action="store_true", help="Skip opening the SSH tunnel (backend already reachable)")
    fp16 = parser.add_mutually_exclusive_group()
    fp16.add_argument(
        "--use-fp16", dest="use_fp16", action="store_true", default=True,
        help="Run inference under fp16 (default on; roughly halves VRAM use)",
    )
    fp16.add_argument("--no-fp16", dest="use_fp16", action="store_false")
    args = parser.parse_args()

    if args.adb_path is None:
        args.adb_path = find_adb()
    args.adb_path = os.path.normpath(args.adb_path)
    if not shutil.which(args.adb_path) and not os.path.isfile(args.adb_path):
        print(f"[watch] ERROR: adb not found at '{args.adb_path}'. Pass --adb-path explicitly.", flush=True)
        sys.exit(1)
    print(f"[watch] Using adb: {args.adb_path}", flush=True)

    tunnel: subprocess.Popen | None = None
    if not args.no_tunnel:
        if not args.ssh_host:
            print("[watch] ERROR: no backend host. Pass --ssh-host user@host (or set OQC_SSH_HOST), "
                  "or use --no-tunnel if the backend is already on localhost.", flush=True)
            sys.exit(1)
        tunnel = start_ssh_tunnel(args.ssh_host, args.ssh_port, args.backend_port)
        if not wait_for_backend(args.backend_port):
            print("[watch] ERROR: backend not reachable through tunnel after 20s. Exiting.", flush=True)
            tunnel.terminate()
            sys.exit(1)
        print("[watch] Backend reachable through tunnel.", flush=True)

    state = load_state()
    pending: dict[str, tuple[str, int]] = {}  # session -> (last_fingerprint, stable_count)

    print(f"[watch] Watching {DEVICE_FILES_ROOT} on device for finished sessions "
          f"(poll every {args.poll_interval}s). Ctrl+C to stop.", flush=True)

    try:
        with tempfile.TemporaryDirectory(prefix="oqc_sessions_") as tmp:
            tmp_root = Path(tmp)
            while True:
                candidates = list_candidate_sessions(args.adb_path, args.adb_serial)
                for session in candidates:
                    if session in state["processed"]:
                        continue
                    fp = dir_fingerprint(args.adb_path, args.adb_serial, session)
                    if fp is None:
                        continue
                    prev_fp, stable_count = pending.get(session, (None, 0))
                    if fp == prev_fp:
                        stable_count += 1
                    else:
                        stable_count = 0
                    pending[session] = (fp, stable_count)

                    if stable_count >= STABLE_POLLS_REQUIRED:
                        print(f"[watch] Session '{session}' looks finished (stable).", flush=True)
                        try:
                            local_dir = pull_session(args.adb_path, args.adb_serial, session, tmp_root, args.camera)
                            ok = process_session(
                                local_dir, args.backend_port, args.camera, args.adb_path, args.adb_serial,
                                use_fp16=args.use_fp16,
                            )
                            if ok:
                                print(f"[watch] Session '{session}' processed and pushed back. ✓", flush=True)
                            else:
                                print(f"[watch] Session '{session}' processing FAILED (see run.py output above).", flush=True)
                        except Exception as e:
                            print(f"[watch] Session '{session}' errored: {e}", flush=True)
                        finally:
                            state["processed"].append(session)
                            save_state(state)
                            pending.pop(session, None)

                time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        print("\n[watch] Stopping.", flush=True)
    finally:
        if tunnel is not None:
            tunnel.terminate()


if __name__ == "__main__":
    main()
