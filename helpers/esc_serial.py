"""
Control the Hobbywing XR10 ESC via an Arduino Nano over USB serial.

The Nano runs firmware/esc/src/main.cpp. The protocol mirrors the servo
helper, but each value is a RAW PULSE WIDTH in microseconds (1000-2000):

    1000 = full reverse
    1500 = neutral / stop
    2000 = full forward

The ESC expects standard RC servo pulses, so we drive its signal pin with
Servo.writeMicroseconds() on the Nano side. The Nano auto-arms the ESC by
holding 1500 us for 3 seconds in setup().

Run as a standalone interactive tester:
    python3 -m helpers.esc_serial --port /dev/ttyUSB1
"""

import argparse
import sys
import time

import serial

from .calibration import ThrottleCalibration

PULSE_MIN = 1000        # full reverse
PULSE_NEUTRAL = 1500    # stop / idle
PULSE_MAX = 2000        # full forward


class SerialESC:
    def __init__(self, port: str, baud: int = 115200):
        self.ser = serial.Serial(port, baud, timeout=0.1)
        # Nano resets on open, then the sketch itself spends 3 s arming the
        # ESC with a neutral pulse. Wait out both before sending anything.
        time.sleep(5.0)

    def write_pulse(self, pulse_us: int):
        pulse_us = max(PULSE_MIN, min(PULSE_MAX, int(pulse_us)))
        self.ser.write(f"{pulse_us}\n".encode("ascii"))
        self.ser.flush()
        return pulse_us

    def set_throttle(self, percent: float):
        """percent in [-100, 100]. Negative = reverse/brake, positive = forward."""
        percent = max(-100.0, min(100.0, percent))
        if percent >= 0:
            pulse = PULSE_NEUTRAL + (PULSE_MAX - PULSE_NEUTRAL) * (percent / 100.0)
        else:
            pulse = PULSE_NEUTRAL + (PULSE_NEUTRAL - PULSE_MIN) * (percent / 100.0)
        return self.write_pulse(int(pulse))

    def stop(self):
        return self.write_pulse(PULSE_NEUTRAL)

    def close(self):
        self.ser.close()


class ThrottleController:
    """Apply a kickstart pulse when leaving neutral, then settle on a
    calibrated target. Wraps SerialESC; the underlying helper stays
    untouched so the standalone tester still works.
    """

    def __init__(self, esc: SerialESC, calibration: ThrottleCalibration):
        self.esc = esc
        self.cal = calibration
        self._last_percent: float = 0.0
        self._kick_until: float = 0.0  # monotonic seconds

    def update_calibration(self, calibration: ThrottleCalibration) -> None:
        self.cal = calibration

    def set_percent(self, percent: float) -> int:
        """Drive the ESC to a calibrated target. Returns the pulse actually
        sent. A short kickstart fires on transitions from neutral so the
        wheels actually start spinning."""
        percent = max(-100.0, min(100.0, float(percent)))
        now = time.monotonic()

        leaving_neutral = abs(self._last_percent) < 1.0 and abs(percent) >= 1.0
        if leaving_neutral:
            kick_us, kick_ms = self.cal.kick_for(percent)
            self._kick_until = now + (kick_ms / 1000.0)
            self._last_percent = percent
            return self.esc.write_pulse(kick_us)

        if now < self._kick_until and (
            (percent > 0 and self._last_percent > 0)
            or (percent < 0 and self._last_percent < 0)
        ):
            # still inside the kick window in the same direction; hold the kick
            kick_us, _ = self.cal.kick_for(percent)
            self._last_percent = percent
            return self.esc.write_pulse(kick_us)

        self._last_percent = percent
        return self.esc.write_pulse(self.cal.percent_to_us(percent))

    def emergency_stop(self) -> int:
        self._last_percent = 0.0
        self._kick_until = 0.0
        return self.esc.stop()


def _read_key() -> str:
    if sys.platform == "win32":
        import msvcrt
        ch = msvcrt.getch()
        try:
            return ch.decode("ascii", errors="ignore")
        except Exception:
            return ""
    else:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, help="Serial port of the ESC Nano")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--step", type=float, default=5.0,
                        help="Throttle step per keypress (%%)")
    args = parser.parse_args()

    esc = SerialESC(args.port, args.baud)
    throttle = 0.0

    try:
        esc.stop()
        print(
            "Controls:\n"
            f"  w / s : throttle +/- {args.step:g} %\n"
            "  space : stop (neutral)\n"
            "  q     : quit\n"
        )
        print(f"throttle = {throttle:+.0f}%")
        while True:
            key = _read_key()
            if key == "w":
                throttle += args.step
            elif key == "s":
                throttle -= args.step
            elif key == " ":
                throttle = 0.0
            elif key == "q":
                break
            else:
                continue

            throttle = max(-100.0, min(100.0, throttle))
            pulse = esc.set_throttle(throttle)
            print(f"throttle = {throttle:+.0f}%   pulse = {pulse} us")
    finally:
        esc.stop()
        esc.close()
        print("Closed.")


if __name__ == "__main__":
    main()
