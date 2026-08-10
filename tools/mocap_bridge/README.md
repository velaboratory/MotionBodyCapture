# Mo=Cat Studio bridge

Turns an OpenQuestCapture session into human-mocap `.glb` files by running it
through a [Mo=Cat Studio](https://github.com/) backend, in one command instead
of the manual "unzip → figure out a video → click through the web UI → download
each track" dance — and pushes the results straight back onto the headset so
they show up in OpenQuestCapture's own **Playback** tab, in passthrough XR.

This tool doesn't touch Mo=Cat Studio's code at all — it's a plain client of its
existing `/upload`, `/ws/{client_id}`, and `/export/{track_id}` HTTP/WS API, the
same one its own React frontend uses.

## Prerequisites

1. A Mo=Cat Studio backend already running and reachable (it requires Linux +
   an NVIDIA GPU — see `mo-cat-studio-master/backend/pyproject.toml` — this
   bridge does **not** start it for you):

   ```bash
   cd mo-cat-studio-master/backend
   uv run uvicorn main:app --host 0.0.0.0 --port 8001
   ```

2. Python deps for this bridge (separate, lightweight — do **not** install
   into the backend's own pinned CUDA env):

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # or .venv\Scripts\activate on Windows
   pip install -r tools/mocap_bridge/requirements.txt
   ```

3. The `quest-3d-reconstruction` git submodule must be initialized (this
   bridge reuses its YUV→RGB decode math rather than reimplementing it):

   ```bash
   git submodule update --init quest-3d-reconstruction
   ```

4. (Optional, on by default) For the final "push to headset" step: Android
   platform-tools (`adb`) on `PATH`, and the Quest connected over USB with USB
   debugging enabled and the connection authorized (you'll have done this
   already if you've ever sideloaded the app). Skip with `--no-push-to-quest`
   if you'd rather transfer `.glb` files some other way.

## Usage

```bash
python tools/mocap_bridge/run.py \
  --session /path/to/20260809_120000            `# or a path to the exported .zip` \
  --backend-url http://<backend-host>:8001 \
  --camera left
```

This will:
1. Decode the session's raw passthrough `.yuv` frames (one camera, `left` by
   default) into an MP4, using the frames' own timestamps for playback fps.
2. Upload it to the backend and run the multi-person tracker.
3. Download one `track_<id>.glb` per detected person.
4. `adb push` each `.glb` onto the headset, into the folder OpenQuestCapture's
   Playback tab scans (`--no-push-to-quest` to skip this).

Outputs land in `<session>/mocap_export/` (or next to the zip, as
`<zipname>_mocap_export/`, if you passed a `.zip`): `capture.mp4` plus one
`.glb` per person detected in the capture.

Tracking parameters (`--skip-frames`, `--bbox-threshold`, `--use-gpu` /
`--no-gpu`, `--max-age`, etc.) mirror the sliders in the Mo=Cat Studio web UI —
run `python tools/mocap_bridge/run.py --help` for the full list. Defaults match
the frontend's own defaults.

Multiple headsets connected over USB? Pass `--adb-serial <serial>` (from `adb
devices`). Non-standard `adb` location? `--adb-path /path/to/adb`.

## Notes

- Only one camera's footage is sent through (Mo=Cat Studio tracks people from a
  single video, not a stereo pair) — pick whichever eye had the better view of
  your subject with `--camera left|right`.
- Capture is typically ~3 FPS (see the main repo README) — fine for tracking,
  but the resulting animation will look choppy without further
  interpolation/retiming on the Mo=Cat/Blender side.
- If `/export/{track_id}` fails server-side (e.g. no usable MHR params for a
  track), that track is skipped with an error printed, not silently dropped.
- The `adb push` step is best-effort: if `adb` isn't found or the headset
  isn't reachable, you get a warning listing exactly which files didn't make
  it over, not a failed run — every `.glb` is already sitting locally in the
  output dir regardless.
- On-device destination is
  `/sdcard/Android/data/com.samusynth.OpenQuestCapture/files/mocap_playback/`,
  the same app-private external-storage convention session recordings already
  use (no extra Android permission needed).
