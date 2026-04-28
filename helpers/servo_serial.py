"""
Control a steering servo on an Arduino Nano over USB serial.

The Nano runs firmware/servo/src/main.cpp. Servo.write() expects an angle in
degrees (0-180). parseInt() on the Nano consumes digits until it hits a
non-digit, so each value is sent followed by a newline as a terminator.

Run as a standalone interactive tester:
    python3 -m helpers.servo_serial --port /dev/ttyUSB0
"""

import argparse
import sys
import time

import serial

ANGLE_MIN = 50
ANGLE_MAX = 150
ANGLE_CENTER = 100


class SerialServo:
    def __init__(self, port: str, baud: int = 115200):
        self._port = port
        self._baud = baud
        # The Nano resets when the serial port opens; wait for the bootloader
        # to hand over to the sketch before sending anything.
        self.ser = serial.Serial(port, baud, timeout=0.1)
        time.sleep(2.0)

    def _try_reopen(self) -> bool:
        # Brownouts / USB glitches drop the fd mid-run; re-enumerate.
        try:
            self.ser = serial.Serial(self._port, self._baud, timeout=0.1)
            time.sleep(2.0)
            return True
        except (serial.SerialException, OSError):
            self.ser = None
            return False

    def write_angle(self, angle: int):
        angle = max(ANGLE_MIN, min(ANGLE_MAX, int(angle)))
        if self.ser is None and not self._try_reopen():
            return angle
        try:
            self.ser.write(f"{angle}\n".encode("ascii"))
            self.ser.flush()
        except (serial.SerialException, OSError) as e:
            print(f"[servo] write failed ({e}); reconnecting...")
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
            if self._try_reopen():
                try:
                    self.ser.write(f"{angle}\n".encode("ascii"))
                    self.ser.flush()
                except (serial.SerialException, OSError):
                    self.ser = None
        return angle

    def center(self):
        return self.write_angle(ANGLE_CENTER)

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None


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
    parser.add_argument("--port", required=True, help="Serial port of the Nano")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--step", type=int, default=5, help="Degrees per keypress")
    args = parser.parse_args()

    servo = SerialServo(args.port, args.baud)
    angle = ANGLE_CENTER

    try:
        servo.write_angle(angle)
        print(
            "Controls:\n"
            f"  a / d : -/+ {args.step} deg (0 = full left, 180 = full right)\n"
            "  space : center (90 deg)\n"
            "  q     : quit\n"
        )
        print(f"angle = {angle}")
        while True:
            key = _read_key()
            if key == "a":
                angle -= args.step
            elif key == "d":
                angle += args.step
            elif key == " ":
                angle = ANGLE_CENTER
            elif key == "q":
                break
            else:
                continue

            angle = servo.write_angle(angle)
            print(f"angle = {angle}")
    finally:
        servo.center()
        servo.close()
        print("Closed.")


if __name__ == "__main__":
    main()
