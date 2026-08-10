"""CLI: OpenQuestCapture session -> Mo=Cat Studio mocap .glb files.

Usage:
    python tools/mocap_bridge/run.py --session /path/to/session_or_export.zip \\
        --backend-url http://<backend-host>:8001 [--camera left] [--no-gpu] ...

Requires a Mo=Cat Studio backend already running elsewhere (it's Linux + CUDA
pinned -- see mo-cat-studio-master/backend/pyproject.toml -- this tool does not
start it):
    cd mo-cat-studio-master/backend && uv run uvicorn main:app --host 0.0.0.0 --port 8001
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import zipfile
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adb_push import push_files  # noqa: E402
from mocap_client import TRACKER_DEFAULTS, export_track, run_tracking, upload_video  # noqa: E402
from yuv_to_video import convert_session_to_video  # noqa: E402


def resolve_session_dir(session_path: Path, extract_root: Path) -> Path:
    """If `session_path` is a zip (as produced by the in-headset "Export Data"
    menu), unzip it; otherwise treat it as an already-extracted session directory."""
    if session_path.is_file() and session_path.suffix.lower() == ".zip":
        target = extract_root / session_path.stem
        with zipfile.ZipFile(session_path) as zf:
            zf.extractall(target)
        return target
    if session_path.is_dir():
        return session_path
    raise FileNotFoundError(f"Session not found: {session_path}")


def default_output_dir(session_path: Path) -> Path:
    # Zip inputs get extracted into a temp dir that's cleaned up afterward, so
    # outputs must live next to the zip, not inside the extraction.
    if session_path.is_file() and session_path.suffix.lower() == ".zip":
        return session_path.parent / f"{session_path.stem}_mocap_export"
    return session_path / "mocap_export"


def check_backend(backend_url: str) -> None:
    try:
        requests.get(f"{backend_url.rstrip('/')}/state", timeout=5).raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(
            f"Could not reach Mo=Cat Studio backend at {backend_url}.\n"
            "Start it first with (from mo-cat-studio-master/backend, on a Linux/CUDA machine):\n"
            "  uv run uvicorn main:app --host 0.0.0.0 --port 8001"
        ) from e


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", type=Path, required=True, help="Session directory or exported .zip")
    parser.add_argument("--backend-url", default="http://localhost:8001", help="Mo=Cat Studio backend base URL")
    parser.add_argument("--camera", choices=["left", "right"], default="left")
    parser.add_argument("--output-dir", type=Path, default=None, help="Defaults next to the session")

    push = parser.add_mutually_exclusive_group()
    push.add_argument(
        "--push-to-quest",
        dest="push_to_quest",
        action="store_true",
        default=True,
        help="adb-push exported .glb files to the headset's Playback folder (default: on)",
    )
    push.add_argument("--no-push-to-quest", dest="push_to_quest", action="store_false")
    parser.add_argument("--adb-path", default="adb", help="Path to the adb executable (default: 'adb' on PATH)")
    parser.add_argument("--adb-serial", default=None, help="Target a specific device when multiple are connected")

    parser.add_argument("--start-frame", type=int, default=TRACKER_DEFAULTS["start_frame"])
    parser.add_argument("--skip-frames", type=int, default=TRACKER_DEFAULTS["skip_frames"])
    parser.add_argument("--distance-limit", type=float, default=TRACKER_DEFAULTS["distanceLimit"])
    parser.add_argument("--ghosting-threshold", type=float, default=TRACKER_DEFAULTS["ghosting_threshold"])
    parser.add_argument("--bbox-threshold", type=float, default=TRACKER_DEFAULTS["bbox_threshold"])
    parser.add_argument("--resize-factor", type=float, default=TRACKER_DEFAULTS["resize_factor"])
    parser.add_argument("--max-age", type=int, default=TRACKER_DEFAULTS["max_age"])

    gpu = parser.add_mutually_exclusive_group()
    gpu.add_argument("--use-gpu", dest="use_gpu", action="store_true", default=TRACKER_DEFAULTS["use_gpu"])
    gpu.add_argument("--no-gpu", dest="use_gpu", action="store_false")

    face = parser.add_mutually_exclusive_group()
    face.add_argument(
        "--face-recognition",
        dest="enable_face_recognition",
        action="store_true",
        default=TRACKER_DEFAULTS["enable_face_recognition"],
    )
    face.add_argument("--no-face-recognition", dest="enable_face_recognition", action="store_false")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    check_backend(args.backend_url)
    output_dir = args.output_dir or default_output_dir(args.session)

    with tempfile.TemporaryDirectory(prefix="mocap_bridge_") as tmp:
        session_dir = resolve_session_dir(args.session, Path(tmp))

        video_path = output_dir / "capture.mp4"
        convert_session_to_video(session_dir, args.camera, video_path)

        print(f"[run] Uploading {video_path.name} to {args.backend_url} ...")
        server_video_path = upload_video(args.backend_url, video_path)

        overrides = {
            "start_frame": args.start_frame,
            "skip_frames": args.skip_frames,
            "distanceLimit": args.distance_limit,
            "ghosting_threshold": args.ghosting_threshold,
            "bbox_threshold": args.bbox_threshold,
            "resize_factor": args.resize_factor,
            "max_age": args.max_age,
            "use_gpu": args.use_gpu,
            "enable_face_recognition": args.enable_face_recognition,
        }

        print("[run] Running tracker on backend ...")
        track_ids = run_tracking(args.backend_url, server_video_path, overrides)

        if not track_ids:
            print("[run] No people detected in this capture.")
            return 0

        print(f"[run] Detected {len(track_ids)} track(s): {sorted(track_ids)}")
        glb_paths = [export_track(args.backend_url, track_id, output_dir) for track_id in sorted(track_ids)]

    push_warnings: list[str] = []
    if args.push_to_quest:
        print("[run] Pushing .glb files to the headset via adb ...")
        push_warnings = push_files(glb_paths, adb_path=args.adb_path, serial=args.adb_serial)

    print("\nDone.")
    print(f"  Video: {video_path}")
    for p in glb_paths:
        print(f"  GLB:   {p}")
    if args.push_to_quest:
        if push_warnings:
            print("  adb push had problems (glb files are still saved locally above):")
            for w in push_warnings:
                print(f"    - {w}")
        else:
            print("  Pushed to headset: Playback tab should show these now.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
