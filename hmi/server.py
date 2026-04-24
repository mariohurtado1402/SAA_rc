"""
FastAPI HMI server. Exposes:

- GET  /                  static single-page dashboard
- WS   /ws/state          state.snapshot() pushed at ~10 Hz
- GET  /video.mjpg        latest annotated camera frame as MJPEG stream
- POST /api/mode          {"mode": "MANUAL"|"LKA"|"RCCA"}
- POST /api/command       {"throttle_pct": float, "steer_deg": int}
- GET  /api/calibration
- POST /api/calibration   ThrottleCalibration fields
- POST /api/thresholds    {"rcca_threshold_cm", "ldr_on_threshold",
                           "ldr_off_threshold", "lka_gain_deg"}
- POST /api/stop          neutral throttle + center steering
"""

import asyncio
import json
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from adas.state import Mode, SystemState
from helpers.calibration import ThrottleCalibration

STATIC_DIR = Path(__file__).parent / "static"


class FrameBuffer:
    """Holds the latest JPEG bytes from the camera thread."""

    def __init__(self):
        self._jpeg: Optional[bytes] = None
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)

    def update(self, jpeg: bytes) -> None:
        with self._cond:
            self._jpeg = jpeg
            self._cond.notify_all()

    def latest(self) -> Optional[bytes]:
        with self._lock:
            return self._jpeg

    def wait_for_next(self, timeout: float = 1.0) -> Optional[bytes]:
        with self._cond:
            self._cond.wait(timeout=timeout)
            return self._jpeg


def build_app(state: SystemState, frames: FrameBuffer,
              config_path: Path) -> FastAPI:
    app = FastAPI(title="SAA_rc HMI")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    @app.get("/api/state")
    def get_state():
        return state.snapshot()

    @app.post("/api/mode")
    async def set_mode(payload: dict):
        try:
            mode = Mode(payload["mode"])
        except (KeyError, ValueError):
            return JSONResponse({"error": "invalid mode"}, status_code=400)
        with state.lock:
            state.mode = mode
            # safety: returning to MANUAL or switching modes resets command
            state.cmd_throttle_pct = 0.0
            state.cmd_steer_deg = 90
        return {"ok": True, "mode": mode.value}

    @app.post("/api/command")
    async def set_command(payload: dict):
        with state.lock:
            if "throttle_pct" in payload:
                state.cmd_throttle_pct = max(-100.0, min(100.0,
                                                         float(payload["throttle_pct"])))
            if "steer_deg" in payload:
                state.cmd_steer_deg = int(payload["steer_deg"])
        return {"ok": True}

    @app.post("/api/stop")
    async def stop():
        with state.lock:
            state.cmd_throttle_pct = 0.0
            state.cmd_steer_deg = 90
        return {"ok": True}

    @app.get("/api/calibration")
    def get_calibration():
        return state.calibration.to_dict()

    @app.post("/api/calibration")
    async def set_calibration(payload: dict):
        new_cal = ThrottleCalibration.from_dict(payload)
        with state.lock:
            state.calibration = new_cal
        _persist(config_path, state)
        return new_cal.to_dict()

    @app.post("/api/thresholds")
    async def set_thresholds(payload: dict):
        with state.lock:
            if "rcca_threshold_cm" in payload:
                state.rcca_threshold_cm = float(payload["rcca_threshold_cm"])
            if "ldr_on_threshold" in payload:
                state.ldr_on_threshold = int(payload["ldr_on_threshold"])
            if "ldr_off_threshold" in payload:
                state.ldr_off_threshold = int(payload["ldr_off_threshold"])
            if "lka_gain_deg" in payload:
                state.lka_gain_deg = float(payload["lka_gain_deg"])
        _persist(config_path, state)
        return {"ok": True}

    @app.websocket("/ws/state")
    async def ws_state(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                await ws.send_text(json.dumps(state.snapshot()))
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            return
        except Exception:
            return

    @app.get("/video.mjpg")
    def video():
        boundary = b"--frame"

        async def gen():
            loop = asyncio.get_event_loop()
            while True:
                jpeg = await loop.run_in_executor(None, frames.wait_for_next, 1.0)
                if not jpeg:
                    # send a keepalive blank to avoid the browser closing the
                    # connection if the camera hasn't produced a frame yet
                    await asyncio.sleep(0.1)
                    continue
                yield (boundary + b"\r\n"
                       b"Content-Type: image/jpeg\r\n"
                       b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                       + jpeg + b"\r\n")

        return StreamingResponse(
            gen(),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    return app


def _persist(path: Path, state: SystemState) -> None:
    """Write the user-tunable parts of state back to config.json."""
    try:
        existing = json.loads(path.read_text()) if path.exists() else {}
    except json.JSONDecodeError:
        existing = {}
    existing["calibration"] = state.calibration.to_dict()
    existing["rcca_threshold_cm"] = state.rcca_threshold_cm
    existing["ldr_thresholds"] = {
        "on": state.ldr_on_threshold,
        "off": state.ldr_off_threshold,
    }
    existing["lka_gain"] = state.lka_gain_deg
    existing.setdefault("proximity_labels", state.proximity_labels)
    path.write_text(json.dumps(existing, indent=2))
