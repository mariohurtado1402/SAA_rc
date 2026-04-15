"""
Control a servo on an Arduino Nano over serial.

The Nano is running this sketch:

    #include <Servo.h>
    Servo myservo;
    void setup() {
      Serial.begin(115200);
      Serial.setTimeout(10);
      myservo.attach(5);
    }
    void loop() {
      if (Serial.available() > 0) {
        int value = Serial.parseInt();
        myservo.write(value);
      }
    }

Servo.write() expects an angle 0-180 degrees. parseInt() consumes digits until
it hits a non-digit, so every value is sent followed by a newline as a
terminator.

Install:
    pip install pyserial

Run:
    python3 servo_serial.py --port COM3           # Windows
    python3 servo_serial.py --port /dev/ttyUSB0   # Linux (Nano clones)
    python3 servo_serial.py --port /dev/ttyACM0   # Linux (genuine Nano)
"""

import argparse
import sys
import time

import serial

ANGLE_MIN = 0
ANGLE_MAX = 180
ANGLE_CENTER = 90


class SerialServo:
    def __init__(self, port: str, baud: int = 115200):
        # The Nano resets when the serial port opens; wait for the bootloader
        # to hand over to the sketch before sending anything.
        self.ser = serial.Serial(port, baud, timeout=0.1)
        time.sleep(2.0)

    def write_angle(self, angle: int):
        angle = max(ANGLE_MIN, min(ANGLE_MAX, int(angle)))
        # Newline terminates parseInt() promptly instead of waiting for the
        # 10 ms Serial.setTimeout() on the Nano side.
        self.ser.write(f"{angle}\n".encode("ascii"))
        self.ser.flush()
        return angle

    def close(self):
        self.ser.close()


def _read_key() -> str:
    """Read one keypress without waiting for Enter, cross-platform."""
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
        servo.write_angle(ANGLE_CENTER)
        servo.close()
        print("Closed.")


if __name__ == "__main__":
    main()
