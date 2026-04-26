"""
Proximity / parking-sensor Nano helper.

The Nano runs firmware/proximity/src/main.cpp at 115200 baud. Every cycle
(~150 ms) it streams one line:

    L: 12 cm	C: 45 cm	R: 78 cm

Distances are integer centimeters; out-of-range pings come through as 0.
The three sensors are all rear-facing (left / center / right).

The Nano now accepts a single ASCII byte to gate its LEDs + buzzer:
    '1' -> alerts ON   (will beep when something < 25 cm)
    '0' -> alerts OFF  (silent, distance stream still flows)
The firmware boots with alerts OFF so the buzzer doesn't beep until the
driver explicitly enables the backup ADAS from the HMI.

Run as a standalone tester:
    uv run python -m helpers.proximity_serial --port COM6
"""

import argparse
import re
import threading
import time
from typing import Callable, Optional, Tuple

import serial

LINE_RE = re.compile(
    r"L:\s*(\d+)\s*cm\s*C:\s*(\d+)\s*cm\s*R:\s*(\d+)\s*cm",
    re.IGNORECASE,
)


class SerialProximity:
    def __init__(self, port: str, baud: int = 115200,
                 on_reading: Optional[Callable[[Tuple[float, float, float]], None]] = None):
        self.ser = serial.Serial(port, baud, timeout=0.2)
        time.sleep(2.0)  # Nano resets on open
        self._on_reading = on_reading
        self._latest: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._alerts_on = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        # Make sure the Nano knows the desired startup state (silent).
        self.set_alerts(False)

    def _read_loop(self):
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = self.ser.read(128)
            except (serial.SerialException, OSError):
                break
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                m = LINE_RE.search(line.decode("ascii", errors="ignore"))
                if not m:
                    continue
                try:
                    left, center, right = (float(m.group(i)) for i in (1, 2, 3))
                except ValueError:
                    continue
                self._latest = (left, center, right)
                if self._on_reading:
                    try:
                        self._on_reading(self._latest)
                    except Exception:
                        pass

    @property
    def latest(self) -> Tuple[float, float, float]:
        return self._latest

    @property
    def alerts_on(self) -> bool:
        return self._alerts_on

    def set_alerts(self, on: bool) -> None:
        """Gate the Arduino's LEDs + buzzer. Idempotent."""
        try:
            self.ser.write(b"1" if on else b"0")
            self.ser.flush()
            self._alerts_on = on
        except (serial.SerialException, OSError):
            pass

    def close(self):
        # Be polite: silence the buzzer on shutdown.
        try:
            self.set_alerts(False)
        except Exception:
            pass
        self._stop.set()
        try:
            self.ser.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--alerts", action="store_true",
                        help="Enable LEDs + buzzer (default: silent stream only)")
    args = parser.parse_args()

    prox = SerialProximity(args.port, args.baud)
    if args.alerts:
        prox.set_alerts(True)
    print("Streaming proximity. Press Ctrl-C to quit.")
    try:
        while True:
            l, c, r = prox.latest
            print(f"L = {l:5.0f} cm   C = {c:5.0f} cm   R = {r:5.0f} cm   "
                  f"alerts = {prox.alerts_on}")
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        prox.close()
        print("\nClosed.")


if __name__ == "__main__":
    main()
