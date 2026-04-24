"""
Proximity Nano helper.

The Nano runs firmware/proximity/src/main.cpp at 115200 baud. Every ~200 ms
it streams one line:

    S1: 12.3 S2: 45.6 S3: 78.9

Distances are in centimeters; out-of-range pings come through as 0.0. The
Nano is output-only — there's no command channel.

By convention used elsewhere in this project:
    S1 = front, S2 = rear-left, S3 = rear-right
The labels are configurable via the host (config.json -> proximity_labels).

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
    r"S1:\s*([-\d.]+)\s+S2:\s*([-\d.]+)\s+S3:\s*([-\d.]+)"
)


class SerialProximity:
    def __init__(self, port: str, baud: int = 115200,
                 on_reading: Optional[Callable[[Tuple[float, float, float]], None]] = None):
        self.ser = serial.Serial(port, baud, timeout=0.2)
        time.sleep(2.0)
        self._on_reading = on_reading
        self._latest: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

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
                    s1, s2, s3 = (float(m.group(i)) for i in (1, 2, 3))
                except ValueError:
                    continue
                self._latest = (s1, s2, s3)
                if self._on_reading:
                    try:
                        self._on_reading(self._latest)
                    except Exception:
                        pass

    @property
    def latest(self) -> Tuple[float, float, float]:
        return self._latest

    def close(self):
        self._stop.set()
        try:
            self.ser.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    prox = SerialProximity(args.port, args.baud)
    print("Streaming proximity. Press Ctrl-C to quit.")
    try:
        while True:
            s1, s2, s3 = prox.latest
            print(f"S1 = {s1:6.1f} cm   S2 = {s2:6.1f} cm   S3 = {s3:6.1f} cm")
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        prox.close()
        print("\nClosed.")


if __name__ == "__main__":
    main()
