"""
SAA_rc command multiplexer + ADAS HMI.

Wires every subsystem (ESC, servo, LDR, proximity, camera) into a single
process that exposes a browser-based HMI on port 8000 by default.

    uv run python cmd_mux.py \
        --esc-port COM3 --servo-port COM4 \
        --ldr-port COM5 --proximity-port COM6 \
        --camera 0

Any --*-port flag may be omitted; that subsystem will be disabled and the
HMI will grey out the corresponding tile. CLI flags override config.json.
"""

import argparse
import json
import threading
import time
from pathlib import Path

import cv2
import uvicorn

from adas import ControlLoop, Mode, SystemState
from helpers import (
    LaneVision,
    SerialESC,
    SerialLDR,
    SerialProximity,
    SerialServo,
    ThrottleCalibration,
    ThrottleController,
)
from hmi import FrameBuffer, build_app

CONFIG_PATH = Path(__file__).parent / "config.json"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--esc-port")
    p.add_argument("--servo-port")
    p.add_argument("--ldr-port")
    p.add_argument("--proximity-port")
    p.add_argument("--camera", type=int)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--config", default=str(CONFIG_PATH))
    return p.parse_args()


def load_config(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            print(f"warning: {path} is not valid JSON, ignoring")
    return {}


def merge_ports(args, cfg: dict) -> dict:
    cfg_ports = cfg.get("ports", {}) or {}
    return {
        "esc": args.esc_port or cfg_ports.get("esc"),
        "servo": args.servo_port or cfg_ports.get("servo"),
        "ldr": args.ldr_port or cfg_ports.get("ldr"),
        "proximity": args.proximity_port or cfg_ports.get("proximity"),
        "camera": args.camera if args.camera is not None else cfg_ports.get("camera", 0),
    }


def camera_thread(vision: LaneVision, state: SystemState, frames: FrameBuffer,
                  stop: threading.Event):
    while not stop.is_set():
        result = vision.read()
        if result is None:
            time.sleep(0.05)
            continue
        with state.lock:
            state.lane_diff = result.diff
            state.lane_bias = result.bias
            state.lane_action = result.action
        ok, jpeg = cv2.imencode(".jpg", result.annotated,
                                [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if ok:
            frames.update(jpeg.tobytes())


def main():
    args = parse_args()
    cfg_path = Path(args.config)
    cfg = load_config(cfg_path)
    ports = merge_ports(args, cfg)

    state = SystemState()
    state.calibration = ThrottleCalibration.from_dict(cfg.get("calibration", {})) \
        if cfg.get("calibration") else ThrottleCalibration()
    state.rcca_threshold_cm = float(cfg.get("rcca_threshold_cm", 25.0))
    ldr_th = cfg.get("ldr_thresholds", {}) or {}
    state.ldr_on_threshold = int(ldr_th.get("on", 400))
    state.ldr_off_threshold = int(ldr_th.get("off", 500))
    state.lka_gain_deg = float(cfg.get("lka_gain", 30.0))
    state.rcca_test_throttle_pct = float(cfg.get("rcca_test_throttle_pct", -20.0))
    state.proximity_labels = list(cfg.get("proximity_labels",
                                          ["rear_left", "rear_center", "rear_right"]))
    state.distances = {label: 0.0 for label in state.proximity_labels}

    # ---- Bring up subsystems ----
    esc = throttle = servo = ldr = proximity = vision = None
    cam_thread = stop_evt = None
    frames = FrameBuffer()

    try:
        if ports["esc"]:
            print(f"Opening ESC on {ports['esc']} ...")
            esc = SerialESC(ports["esc"])
            throttle = ThrottleController(esc, state.calibration)
            state.has_esc = True

        if ports["servo"]:
            print(f"Opening servo on {ports['servo']} ...")
            servo = SerialServo(ports["servo"])
            state.has_servo = True

        if ports["ldr"]:
            print(f"Opening LDR on {ports['ldr']} ...")
            def on_ldr(value: int):
                with state.lock:
                    state.ldr_value = value
            ldr = SerialLDR(ports["ldr"], on_value=on_ldr)
            state.has_ldr = True

        if ports["proximity"]:
            print(f"Opening proximity on {ports['proximity']} ...")
            labels = state.proximity_labels
            def on_prox(reading):
                with state.lock:
                    for i, label in enumerate(labels):
                        state.distances[label] = reading[i]
            proximity = SerialProximity(ports["proximity"], on_reading=on_prox)
            state.has_proximity = True

        if ports["camera"] is not None:
            try:
                print(f"Opening camera index {ports['camera']} ...")
                vision = LaneVision(ports["camera"])
                state.has_camera = True
                stop_evt = threading.Event()
                cam_thread = threading.Thread(
                    target=camera_thread, args=(vision, state, frames, stop_evt),
                    daemon=True,
                )
                cam_thread.start()
            except RuntimeError as e:
                print(f"warning: camera unavailable: {e}")

        # ---- Sync calibration changes back into the throttle controller ----
        # The HMI replaces state.calibration on save; reflect that into the
        # live controller too. Cheap to do every 200 ms.
        def cal_sync():
            while True:
                time.sleep(0.2)
                if throttle:
                    with state.lock:
                        cal = state.calibration
                    throttle.update_calibration(cal)
        threading.Thread(target=cal_sync, daemon=True).start()

        # ---- Control loop ----
        loop = ControlLoop(state, throttle, servo, ldr=ldr, proximity=proximity)
        loop.start()

        # ---- Web app ----
        app = build_app(state, frames, cfg_path)
        print(f"\nHMI: http://{args.host}:{args.port}/  (mode = {state.mode.value})\n")
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")

    finally:
        print("\nShutting down ...")
        if stop_evt:
            stop_evt.set()
        try:
            loop.stop()
        except Exception:
            pass
        for closer in (vision, proximity, ldr, servo, esc):
            try:
                if closer is not None:
                    closer.close() if hasattr(closer, "close") else None
            except Exception:
                pass
        print("Stopped.")


if __name__ == "__main__":
    main()
