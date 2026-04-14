"""
Control Hobbywing XR10 ESC (17.5T motor) from a Raspberry Pi 4.

Wiring:
    ESC signal wire (white/yellow) -> Pi GPIO18 (pin 12)
    ESC ground wire  (black/brown) -> Pi GND    (pin 6)
    DO NOT connect the ESC's red/BEC wire to the Pi 5V rail.

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

# Standard RC servo pulse widths (microseconds) at 50 Hz.
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
    pi = pigpio.pi()
    if not pi.connected:
        print("Cannot connect to pigpiod. Run: sudo systemctl start pigpiod")
        sys.exit(1)

    esc = ESC(pi)
    throttle = 0.0
    step = 5.0

    try:
        esc.arm()
        print(
            "Controls:\n"
            "  w / s : throttle +/-\n"
            "  space : stop (neutral)\n"
            "  q     : quit\n"
        )
        while True:
            key = _read_key()
            if key == "w":
                throttle += step
            elif key == "s":
                throttle -= step
            elif key == " ":
                throttle = 0.0
            elif key == "q":
                break
            else:
                continue

            throttle = max(-100.0, min(100.0, throttle))
            esc.set_throttle(throttle)
            print(f"throttle = {throttle:+.0f}%")
    finally:
        esc.stop()
        time.sleep(0.2)
        esc.shutdown()
        pi.stop()
        print("Stopped.")


if __name__ == "__main__":
    main()
