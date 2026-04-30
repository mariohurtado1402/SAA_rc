"""
Periodic control loop. Runs at 50 Hz on its own thread, reading the shared
SystemState plus latest sensor data and emitting throttle/steer commands.
"""

import threading
import time
from typing import Optional

from helpers import (
    SerialServo,
    ThrottleController,
    bias_to_angle,
)

from .state import Mode, SystemState

LOOP_HZ = 50


class ControlLoop:
    def __init__(self, state: SystemState,
                 throttle: Optional[ThrottleController],
                 servo: Optional[SerialServo],
                 ldr=None,
                 proximity=None):
        self.state = state
        self.throttle = throttle
        self.servo = servo
        self.ldr = ldr
        self.proximity = proximity
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        if self.throttle:
            self.throttle.emergency_stop()
        if self.servo:
            self.servo.center()

    def _run(self):
        period = 1.0 / LOOP_HZ
        next_tick = time.monotonic()
        while not self._stop.is_set():
            self._tick()
            next_tick += period
            sleep = next_tick - time.monotonic()
            if sleep > 0:
                time.sleep(sleep)
            else:
                next_tick = time.monotonic()

    def _tick(self):
        s = self.state
        with s.lock:
            mode = s.mode
            cmd_throttle = s.cmd_throttle_pct
            cmd_steer = s.cmd_steer_deg
            ldr_value = s.ldr_value
            ldr_on = s.ldr_on_threshold
            ldr_off = s.ldr_off_threshold
            headlight = s.headlight_on
            distances = dict(s.distances)
            rcca_threshold = s.rcca_threshold_cm
            rcca_test_pct = s.rcca_test_throttle_pct
            lane_bias = s.lane_bias
            lka_gain = s.lka_gain_deg
            lka_deadzone = s.lka_deadzone

        # 1) Headlights — hysteresis around the LDR threshold.
        # Lower ADC reading = darker, so flip MOSFET ON when value falls
        # below `on` and OFF when it rises above `off` (off > on).
        new_headlight = headlight
        if ldr_value <= ldr_on:
            new_headlight = True
        elif ldr_value >= ldr_off:
            new_headlight = False
        if new_headlight != headlight and self.ldr is not None:
            self.ldr.set_mosfet(new_headlight)
        with s.lock:
            s.headlight_on = new_headlight

        # 1b) Backup ADAS gate — sync the proximity Nano's alerts to whatever
        # the driver toggled in the HMI.
        if self.proximity is not None:
            with s.lock:
                want_alerts = s.proximity_alerts_on
            if self.proximity.alerts_on != want_alerts:
                self.proximity.set_alerts(want_alerts)

        # 2) Resolve throttle + steering by mode
        target_throttle = cmd_throttle
        target_steer = cmd_steer

        if mode is Mode.LKA and lane_bias is not None:
            target_steer = bias_to_angle(lane_bias, lka_deadzone, lka_gain)

        elif mode is Mode.RCCA:
            # Test cruise: hold a slow auto-reverse so the safety brake is
            # exercised without the user holding the throttle slider.
            target_throttle = rcca_test_pct

        # 2b) Always-on rear collision brake. Independent of mode: any time
        # the car is being asked to reverse and any rear sensor reads under
        # the threshold, we drop the ESC to neutral.
        rcca_brake = False
        if target_throttle < 0:
            rear_min = self._min_rear_distance(distances)
            if rear_min is not None and 0 < rear_min < rcca_threshold:
                target_throttle = 0.0
                rcca_brake = True

        # 3) Apply
        applied_us = None
        if self.throttle is not None:
            applied_us = self.throttle.set_percent(target_throttle)
        applied_deg = target_steer
        if self.servo is not None:
            applied_deg = self.servo.write_angle(target_steer)

        with s.lock:
            if applied_us is not None:
                s.applied_esc_us = applied_us
            s.applied_servo_deg = applied_deg
            s.rcca_brake = rcca_brake

    @staticmethod
    def _min_rear_distance(distances: dict) -> Optional[float]:
        rear = [v for k, v in distances.items()
                if k.startswith("rear") and v > 0]
        return min(rear) if rear else None
