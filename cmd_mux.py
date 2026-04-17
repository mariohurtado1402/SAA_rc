"""
Command multiplexer: WASD keyboard -> two Arduino Nanos over USB serial.

    w / s  -> throttle via the ESC Nano     (firmware/esc/src/main.cpp)
    a / d  -> steering via the servo Nano   (firmware/servo/src/main.cpp)
    space  -> stop + center
    q      -> quit (stops ESC, centers servo, closes ports)

The ESC Nano arms automatically at boot (3 s neutral pulse).

Run:
    uv run cmd_mux.py -- \
        --esc-port   /dev/ttyUSB0 \
        --servo-port /dev/ttyUSB1
"""

import argparse
import sys

from helpers import (
    SerialServo,
    SerialESC,
    ANGLE_CENTER,
    ANGLE_MIN,
    ANGLE_MAX,
)


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
    parser.add_argument("--esc-port", default=None,
                        help="Serial port of the ESC Nano (e.g. /dev/ttyUSB0)")
    parser.add_argument("--servo-port", default=None,
                        help="Serial port of the servo Nano (e.g. /dev/ttyUSB1)")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--throttle-step", type=float, default=5.0)
    parser.add_argument("--steering-step", type=int, default=10,
                        help="Degrees per a/d press")
    args = parser.parse_args()

    if not args.esc_port and not args.servo_port:
        parser.error("provide at least one of --esc-port or --servo-port")

    esc = SerialESC(args.esc_port, args.baud) if args.esc_port else None
    servo = SerialServo(args.servo_port, args.baud) if args.servo_port else None

    throttle = 0.0
    angle = ANGLE_CENTER

    try:
        if esc:
            esc.stop()
        if servo:
            servo.write_angle(angle)

        controls = []
        if esc:
            controls.append(f"  w / s : throttle  +/- {args.throttle_step:g} %")
        if servo:
            controls.append(
                f"  a / d : steering  -/+ {args.steering_step} deg "
                "(0 = left, 90 = center, 180 = right)"
            )
        controls.append("  space : stop / center")
        controls.append("  q     : quit")
        print("Controls:\n" + "\n".join(controls) + "\n")

        while True:
            key = _read_key()
            if key == "w" and esc:
                throttle += args.throttle_step
            elif key == "s" and esc:
                throttle -= args.throttle_step
            elif key == "a" and servo:
                angle -= args.steering_step
            elif key == "d" and servo:
                angle += args.steering_step
            elif key == " ":
                throttle = 0.0
                angle = ANGLE_CENTER
            elif key == "q":
                break
            else:
                continue

            throttle = max(-100.0, min(100.0, throttle))
            angle = max(ANGLE_MIN, min(ANGLE_MAX, angle))

            pulse = esc.set_throttle(throttle) if esc else None
            if servo:
                angle = servo.write_angle(angle)

            parts = []
            if esc:
                parts.append(f"throttle = {throttle:+.0f}% ({pulse} us)")
            if servo:
                parts.append(f"steering = {angle} deg")
            print("   ".join(parts))
    finally:
        if esc:
            esc.stop()
            esc.close()
        if servo:
            servo.center()
            servo.close()
        print("Stopped.")


if __name__ == "__main__":
    main()
