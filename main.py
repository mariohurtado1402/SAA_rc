"""
Control Hobbywing XR10 ESC (17.5T motor) + steering servo from a Raspberry Pi 4.

Wiring:
    ESC signal    (white/yellow) -> Pi GPIO18 (pin 12)
    ESC ground    (black/brown)  -> Pi GND    (pin 6)
    Servo signal  (white/yellow) -> Pi GPIO17 (pin 11)
    Servo V+      (red)          -> ESC BEC 5-6 V (or external 5 V BEC)
    Servo ground  (black/brown)  -> same GND rail as the Pi
    DO NOT connect the ESC's red/BEC wire to the Pi 5V rail.
    All grounds (Pi, ESC, servo) must be tied together.

Requires pigpio (hardware-timed servo pulses, no jitter):
    sudo apt install pigpio python3-pigpio
    sudo systemctl enable --now pigpiod

Run:
    python3 main.py
"""

import sys
import time
import termios
import tty

import pigpio

ESC_GPIO = 18
SERVO_GPIO = 17

# Standard RC pulse widths (microseconds) at 50 Hz.
# XR10 in "slowest" profile still uses the same pulse range; the profile
# limits how aggressively the ESC maps pulse -> motor output.
PULSE_NEUTRAL = 1500
PULSE_FULL_FWD = 2000
PULSE_FULL_REV = 1000
PULSE_OFF = 0  # tells pigpio to stop sending pulses

# Steering servo travel. Many RC cars clip internally; 1000-2000 us is the
# safe standard. Narrow this if the servo buzzes against the end stops.
SERVO_CENTER = 1500
SERVO_LEFT = 1000   # full left
SERVO_RIGHT = 2000  # full right


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


class Servo:
    """Steering servo. Position in [-100, 100] (left -> right)."""

    def __init__(self, pi: pigpio.pi, gpio: int = SERVO_GPIO):
        self.pi = pi
        self.gpio = gpio

    def set_position(self, percent: float):
        percent = max(-100.0, min(100.0, percent))
        if percent >= 0:
            pulse = SERVO_CENTER + (SERVO_RIGHT - SERVO_CENTER) * (percent / 100.0)
        else:
            pulse = SERVO_CENTER + (SERVO_CENTER - SERVO_LEFT) * (percent / 100.0)
        self.pi.set_servo_pulsewidth(self.gpio, int(pulse))

    def center(self):
        self.pi.set_servo_pulsewidth(self.gpio, SERVO_CENTER)

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
    pi = pigpio.pi()
    if not pi.connected:
        print("Cannot connect to pigpiod. Run: sudo systemctl start pigpiod")
        sys.exit(1)

    esc = ESC(pi)
    servo = Servo(pi)

    throttle = 0.0
    steering = 0.0
    throttle_step = 5.0
    steering_step = 10.0

    try:
        esc.arm()
        servo.center()
        print(
            "Controls:\n"
            "  w / s : throttle  forward / back\n"
            "  a / d : steering  left    / right\n"
            "  space : stop throttle + center steering\n"
            "  q     : quit\n"
        )
        while True:
            key = _read_key()
            if key == "w":
                throttle += throttle_step
            elif key == "s":
                throttle -= throttle_step
            elif key == "a":
                steering -= steering_step
            elif key == "d":
                steering += steering_step
            elif key == " ":
                throttle = 0.0
                steering = 0.0
            elif key == "q":
                break
            else:
                continue

            throttle = max(-100.0, min(100.0, throttle))
            steering = max(-100.0, min(100.0, steering))
            esc.set_throttle(throttle)
            servo.set_position(steering)
            print(f"throttle = {throttle:+.0f}%   steering = {steering:+.0f}%")
    finally:
        esc.stop()
        servo.center()
        time.sleep(0.2)
        esc.shutdown()
        servo.shutdown()
        pi.stop()
        print("Stopped.")


if __name__ == "__main__":
    main()
