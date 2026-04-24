"""
Thread-safe shared state for the ADAS stack. The control loop, sensor
threads, camera thread and HMI server all read/write this object.
"""

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from helpers.calibration import ThrottleCalibration


class Mode(str, Enum):
    MANUAL = "MANUAL"
    LKA = "LKA"
    RCCA = "RCCA"


@dataclass
class SystemState:
    mode: Mode = Mode.MANUAL

    # LDR / headlight
    ldr_value: int = 0
    headlight_on: bool = False
    ldr_on_threshold: int = 400
    ldr_off_threshold: int = 500

    # Ultrasonic distances in cm; key = configurable label
    distances: dict = field(default_factory=lambda: {
        "front": 0.0, "rear_left": 0.0, "rear_right": 0.0
    })
    rcca_threshold_cm: float = 25.0

    # Lane vision
    lane_diff: Optional[int] = None
    lane_bias: Optional[float] = None
    lane_action: str = "None"
    lka_gain_deg: float = 30.0  # max servo deviation from center

    # User commands (from HMI)
    cmd_throttle_pct: float = 0.0
    cmd_steer_deg: int = 90

    # Last applied outputs
    applied_esc_us: int = 1500
    applied_servo_deg: int = 90
    rcca_brake: bool = False

    # Subsystem availability (set by cmd_mux at startup)
    has_esc: bool = False
    has_servo: bool = False
    has_ldr: bool = False
    has_proximity: bool = False
    has_camera: bool = False

    # Calibration profile (separate object so it round-trips through the HMI)
    calibration: ThrottleCalibration = field(default_factory=ThrottleCalibration)
    proximity_labels: list = field(default_factory=lambda: ["front", "rear_left", "rear_right"])

    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def snapshot(self) -> dict:
        """Plain-dict view safe to JSON-encode."""
        with self.lock:
            return {
                "mode": self.mode.value,
                "ldr": {
                    "value": self.ldr_value,
                    "headlight_on": self.headlight_on,
                    "on_threshold": self.ldr_on_threshold,
                    "off_threshold": self.ldr_off_threshold,
                },
                "distances": dict(self.distances),
                "rcca_threshold_cm": self.rcca_threshold_cm,
                "lane": {
                    "diff": self.lane_diff,
                    "bias": self.lane_bias,
                    "action": self.lane_action,
                    "gain_deg": self.lka_gain_deg,
                },
                "command": {
                    "throttle_pct": self.cmd_throttle_pct,
                    "steer_deg": self.cmd_steer_deg,
                },
                "applied": {
                    "esc_us": self.applied_esc_us,
                    "servo_deg": self.applied_servo_deg,
                    "rcca_brake": self.rcca_brake,
                },
                "availability": {
                    "esc": self.has_esc,
                    "servo": self.has_servo,
                    "ldr": self.has_ldr,
                    "proximity": self.has_proximity,
                    "camera": self.has_camera,
                },
                "calibration": self.calibration.to_dict(),
                "proximity_labels": list(self.proximity_labels),
            }
