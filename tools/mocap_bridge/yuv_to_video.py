"""Convert an OpenQuestCapture session's raw passthrough YUV frames into an MP4.

Reuses the YUV_420_888 -> BGR plane math from the quest-3d-reconstruction
submodule (scripts/utils/image_utils.py::convert_yuv420_888_to_bgr) instead of
reimplementing Android's per-plane rowStride/pixelStride handling.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import median

import cv2
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RECON_SCRIPTS = _REPO_ROOT / "quest-3d-reconstruction" / "scripts"
if str(_RECON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_RECON_SCRIPTS))

from models.image_format_info import BaseTime, ImageFormatInfo, ImagePlaneInfo  # noqa: E402
from utils.image_utils import convert_yuv420_888_to_bgr  # noqa: E402

CAMERA_RAW_DIR = {"left": "left_camera_raw", "right": "right_camera_raw"}
CAMERA_FORMAT_JSON = {"left": "left_camera_image_format.json", "right": "right_camera_image_format.json"}


def load_format_info(session_dir: Path, camera: str) -> ImageFormatInfo:
    format_json_path = session_dir / CAMERA_FORMAT_JSON[camera]
    if not format_json_path.exists():
        raise FileNotFoundError(
            f"Missing {format_json_path.name} in {session_dir} -- is this an OpenQuestCapture session folder?"
        )
    with open(format_json_path) as f:
        info = json.load(f)

    planes = [
        ImagePlaneInfo(
            buffer_size=p["bufferSize"],
            row_stride=p["rowStride"],
            pixel_stride=p["pixelStride"],
        )
        for p in info["planes"]
    ]
    base_time = BaseTime(
        mono_time_ns=info["baseTime"]["baseMonoTimeNs"],
        unix_time_ns=info["baseTime"]["baseUnixTimeMs"],
    )
    return ImageFormatInfo(
        width=info["width"],
        height=info["height"],
        format=info["format"],
        planes=planes,
        base_time=base_time,
    )


def list_frames(session_dir: Path, camera: str) -> list[tuple[int, Path]]:
    raw_dir = session_dir / CAMERA_RAW_DIR[camera]
    if not raw_dir.is_dir():
        raise FileNotFoundError(f"Missing {raw_dir} -- is this an OpenQuestCapture session folder?")
    frames = [(int(p.stem), p) for p in raw_dir.glob("*.yuv")]
    frames.sort(key=lambda item: item[0])
    if not frames:
        raise FileNotFoundError(f"No .yuv frames found in {raw_dir}")
    return frames


def estimate_fps(timestamps_ms: list[int], default: float = 3.0) -> float:
    """Derive playback fps from actual capture timestamps (capture runs at a
    configurable, typically low, fixed rate -- see OpenQuestCapture's README)."""
    if len(timestamps_ms) < 2:
        return default
    deltas = [b - a for a, b in zip(timestamps_ms, timestamps_ms[1:]) if b > a]
    if not deltas:
        return default
    delta_ms = median(deltas)
    if delta_ms <= 0:
        return default
    return 1000.0 / delta_ms


def convert_session_to_video(session_dir: Path, camera: str, output_path: Path) -> Path:
    """Decode a session's raw YUV_420_888 frames (one camera) into an MP4, in timestamp order."""
    format_info = load_format_info(session_dir, camera)
    frames = list_frames(session_dir, camera)
    fps = estimate_fps([ts for ts, _ in frames])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = None
    try:
        for _timestamp, frame_path in frames:
            raw = np.fromfile(frame_path, dtype=np.uint8)
            bgr = convert_yuv420_888_to_bgr(raw_data=raw, format_info=format_info)

            if writer is None:
                height, width = bgr.shape[:2]
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
                if not writer.isOpened():
                    raise RuntimeError(f"Failed to open video writer for {output_path}")

            writer.write(bgr)
    finally:
        if writer is not None:
            writer.release()

    print(f"[yuv_to_video] Wrote {len(frames)} frames at {fps:.2f} fps -> {output_path}")
    return output_path
