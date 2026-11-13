"""Client for the Mo=Cat Studio backend: upload a video, run the tracker, and
export one .glb per detected person.

Talks to an already-running backend (see mo-cat-studio-master/backend) over the
same HTTP/WS API its own frontend uses. This module makes no changes to that
project -- it's purely a client of its existing /upload, /ws/{client_id}, and
/export/{track_id} contract.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import requests
import websocket  # from the `websocket-client` package

# Mirrors the `defaults` object in
# mo-cat-studio-master/frontend/src/hooks/useMocapControls.ts, and the field
# names main.py's websocket "start" handler reads (mixed snake_case/camelCase
# intentionally kept as-is to match the backend contract).
TRACKER_DEFAULTS: dict[str, Any] = {
    "start_frame": 0,
    "skip_frames": 1,
    "distanceLimit": 20.0,
    "ghosting_threshold": 0.25,
    "ghost_3d_threshold": 0.5,
    "hist_match_threshold": 0.3,
    "use_gpu": True,
    "max_age": 30,
    "bbox_threshold": 0.5,
    "resize_factor": 1.0,
    "use_fp16": False,
    "disable_ghost_suppression": False,
    "enable_face_recognition": True,
    "embed_retry_interval": 10,
    "embed_max_retries": 3,
    "embed_quality_threshold": 0.4,
    "gallery_max_age": 300,
    "face_match_threshold": 0.5,
    "maxEmbeddingsPerPerson": 10,
    "embedSimilarityThreshold": 0.9,
}


def upload_video(backend_url: str, video_path: Path) -> str:
    """POST the video to the backend; returns the server-side path to pass to `start`."""
    with open(video_path, "rb") as f:
        response = requests.post(
            f"{backend_url.rstrip('/')}/upload",
            files={"file": (video_path.name, f)},
        )
    response.raise_for_status()
    return response.json()["path"]


def _ws_url(backend_url: str) -> str:
    ws_base = backend_url.rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
    return f"{ws_base}/ws/{uuid.uuid4().hex}"


def run_tracking(backend_url: str, video_path_on_server: str, overrides: dict[str, Any] | None = None) -> set[int]:
    """Run the tracker over an uploaded video; returns the set of detected track ids.

    Streams the same `status`/`frame`/`complete`/`error` messages the web
    frontend consumes (see main.py's `/ws/{client_id}` handler).
    """
    params = {**TRACKER_DEFAULTS, **(overrides or {})}

    # Generous per-message timeout: SAM-3D-Body inference per frame can be slow
    # without a GPU, and this bounds the gap between "frame" messages, not the
    # overall run.
    ws = websocket.create_connection(_ws_url(backend_url), timeout=120)
    track_ids: set[int] = set()
    try:
        ws.send(json.dumps({"type": "start", "video_path": video_path_on_server, **params}))

        while True:
            message = json.loads(ws.recv())
            msg_type = message.get("type")

            if msg_type == "status":
                print(f"[mocap_client] {message.get('message')}")
            elif msg_type == "frame":
                persons = message.get("data", {}).get("persons", {})
                track_ids.update(int(pid) for pid in persons.keys())
            elif msg_type == "complete":
                break
            elif msg_type == "error":
                raise RuntimeError(f"Mo=Cat Studio backend error: {message.get('message')}")
    finally:
        ws.close()

    return track_ids


def export_track(
    backend_url: str, track_id: int, output_dir: Path, fps: float | None = None, smooth: float | None = None
) -> Path:
    """Download the full-track .glb for one tracked person.

    fps is the real rate of the tracked frames. Without it the backend writes
    the animation at 30 fps, which plays a slow capture many times too fast.
    smooth scales the backend's temporal smoothing (1 = default, 0 = raw).
    """
    params = {}
    if fps:
        params["fps"] = fps
    if smooth is not None:
        params["smooth"] = smooth
    params = params or None
    response = requests.get(f"{backend_url.rstrip('/')}/export/{track_id}", params=params)
    response.raise_for_status()

    # On failure the endpoint returns a 200 JSON {"error": ...} body instead of
    # raising, since it doesn't use HTTPException -- detect that case here.
    if "json" in response.headers.get("content-type", ""):
        raise RuntimeError(f"Export failed for track {track_id}: {response.json()}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"track_{track_id}.glb"
    output_path.write_bytes(response.content)
    return output_path
