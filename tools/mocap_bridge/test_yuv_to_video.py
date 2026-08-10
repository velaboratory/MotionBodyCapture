"""Unit test for yuv_to_video.py against a synthetic YUV_420_888 buffer with
known stride values -- doesn't require a real Quest capture."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from yuv_to_video import convert_session_to_video

WIDTH, HEIGHT = 16, 16


def _write_fake_session(session_dir: Path, camera: str) -> None:
    """Build a two-frame fully-planar YUV_420_888 session: flat mid-grey
    (Y=200, U=V=128) so the decoded BGR pixels have a known expected value."""
    raw_dir = session_dir / f"{camera}_camera_raw"
    raw_dir.mkdir(parents=True)

    y_size = WIDTH * HEIGHT
    chroma_w, chroma_h = WIDTH // 2, HEIGHT // 2
    uv_size = chroma_w * chroma_h

    y_plane = np.full(y_size, 200, dtype=np.uint8)
    u_plane = np.full(uv_size, 128, dtype=np.uint8)
    v_plane = np.full(uv_size, 128, dtype=np.uint8)
    frame_bytes = np.concatenate([y_plane, u_plane, v_plane]).tobytes()

    timestamps_ms = [1_000, 1_333]  # ~3 fps
    for ts in timestamps_ms:
        (raw_dir / f"{ts}.yuv").write_bytes(frame_bytes)

    format_info = {
        "width": WIDTH,
        "height": HEIGHT,
        "format": "YUV_420_888",
        "planes": [
            {"rowStride": WIDTH, "pixelStride": 1, "bufferSize": y_size},
            {"rowStride": chroma_w, "pixelStride": 1, "bufferSize": uv_size},
            {"rowStride": chroma_w, "pixelStride": 1, "bufferSize": uv_size},
        ],
        "baseTime": {"baseMonoTimeNs": 0, "baseUnixTimeMs": timestamps_ms[0]},
    }
    (session_dir / f"{camera}_camera_image_format.json").write_text(json.dumps(format_info))


class TestYuvToVideo(unittest.TestCase):
    def test_convert_session_to_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp) / "session"
            _write_fake_session(session_dir, "left")

            output_path = session_dir / "mocap_export" / "capture.mp4"
            convert_session_to_video(session_dir, "left", output_path)

            self.assertTrue(output_path.exists())

            cap = cv2.VideoCapture(str(output_path))
            try:
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                ok, frame = cap.read()
            finally:
                cap.release()

            self.assertEqual(frame_count, 2)
            self.assertAlmostEqual(fps, 1000.0 / 333.0, delta=0.1)

            self.assertTrue(ok)
            self.assertEqual(frame.shape[:2], (HEIGHT, WIDTH))
            # Neutral chroma (U=V=128) -> no color tint, so B/G/R must match each
            # other closely. This is what actually exercises the plane/stride
            # addressing math: a wrong U/V offset would show up as a color cast,
            # not as an absolute brightness shift. We don't assert an exact
            # brightness value against the input Y=200, since OpenCV's
            # COLOR_YUV2BGR_I420 uses limited-range BT.601 scaling
            # (~1.164*(Y-16)), not a raw identity mapping.
            # Tolerance of 10 accounts for mp4v's lossy quantization noise on an
            # otherwise-flat color region, not the decode math itself.
            mean_pixel = frame.reshape(-1, 3).mean(axis=0)
            self.assertLess(mean_pixel.max() - mean_pixel.min(), 10, "expected a neutral gray pixel, got a color tint")
            self.assertGreater(mean_pixel.mean(), 150, "expected a bright pixel for Y=200")

    def test_missing_session_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp) / "missing_session"
            session_dir.mkdir()
            with self.assertRaises(FileNotFoundError):
                convert_session_to_video(session_dir, "left", session_dir / "out.mp4")


if __name__ == "__main__":
    unittest.main()
