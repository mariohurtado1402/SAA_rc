"""
Control Hobbywing XR10 ESC (17.5T motor) from a Raspberry Pi 4, and a steering
servo via an Arduino Nano over USB serial.

Wiring:
    ESC signal    (white/yellow) -> Pi GPIO18 (pin 12)
    ESC ground    (black/brown)  -> Pi GND    (pin 6)
    DO NOT connect the ESC's red/BEC wire to the Pi 5V rail.

    Servo is driven by the Nano (D5). Nano connects to the Pi via USB.
    Servo V+ from ESC BEC, servo GND tied to the ESC/Pi/Nano common ground.

Requires:
    sudo apt install pigpio python3-pigpio
    sudo systemctl enable --now pigpiod
    pip install pyserial

Run:
    python3 main.py --serial-port /dev/ttyUSB0
"""

import argparse
import sys
import time
import termios
import tty

import pigpio

from servo_serial import SerialServo, ANGLE_CENTER, ANGLE_MIN, ANGLE_MAX

ESC_GPIO = 18

# Standard RC pulse widths (microseconds) at 50 Hz.
# XR10 in "slowest" profile still uses the same pulse range; the profile
# limits how aggressively the ESC maps pulse -> motor output.
PULSE_NEUTRAL = 1500
PULSE_FULL_FWD = 2000
PULSE_FULL_REV = 1000
PULSE_OFF = 0  # tells pigpio to stop sending pulses


class ESC:
    def __init__(self, pi: pigpio.pi, gpio: int = ESC_GPIO):
        self.pi = pi
        self.gpio = gpio

    def arm(self):
        """Hold neutral so the ESC completes its startup beeps and arms."""
        print("Arming ESC: holding neutral for 3 s...")
        self.pi.set_servo_pulsewidth(self.gpio, PULSE_NEUTRAL)
        time.sleep(3.0)
        print("ESC armed.")

    def set_throttle(self, percent: float):
        """percent in [-100, 100]. Negative = reverse/brake, positive = forward."""
        percent = max(-100.0, min(100.0, percent))
        if percent >= 0:
            pulse = PULSE_NEUTRAL + (PULSE_FULL_FWD - PULSE_NEUTRAL) * (percent / 100.0)
        else:
            pulse = PULSE_NEUTRAL + (PULSE_NEUTRAL - PULSE_FULL_REV) * (percent / 100.0)
        self.pi.set_servo_pulsewidth(self.gpio, int(pulse))

    def stop(self):
        self.pi.set_servo_pulsewidth(self.gpio, PULSE_NEUTRAL)

    def shutdown(self):
        self.pi.set_servo_pulsewidth(self.gpio, PULSE_OFF)


def _read_key() -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--serial-port",
        required=True,
        help="Serial port of the Arduino Nano (e.g. /dev/ttyUSB0 or COM15)",
    )
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--throttle-step", type=float, default=5.0)
    parser.add_argument("--steering-step", type=int, default=10,
                        help="Degrees per a/d press")
    args = parser.parse_args()

    pi = pigpio.pi()
    if not pi.connected:
        print("Cannot connect to pigpiod. Run: sudo systemctl start pigpiod")
        sys.exit(1)

    esc = ESC(pi)
    servo = SerialServo(args.serial_port, args.baud)

    throttle = 0.0
    angle = ANGLE_CENTER

    try:
        esc.arm()
        servo.write_angle(angle)
        print(
            "Controls:\n"
            f"  w / s : throttle  +/-{args.throttle_step:g} %\n"
            f"  a / d : steering  -/+{args.steering_step} deg (0 = left, 180 = right)\n"
            "  space : stop throttle + center steering\n"
            "  q     : quit\n"
        )
        while True:
            key = _read_key()
            if key == "w":
                throttle += args.throttle_step
            elif key == "s":
                throttle -= args.throttle_step
            elif key == "a":
                angle -= args.steering_step
            elif key == "d":
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
            esc.set_throttle(throttle)
            angle = servo.write_angle(angle)
            print(f"throttle = {throttle:+.0f}%   steering = {angle} deg")
    finally:
        esc.stop()
        servo.write_angle(ANGLE_CENTER)
        time.sleep(0.2)
        esc.shutdown()
        servo.close()
        pi.stop()
        print("Stopped.")


if __name__ == "__main__":
    main()
