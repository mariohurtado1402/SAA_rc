"""
LDR Nano helper.

The Nano runs firmware/LDR/LDR/LDR.ino at 9600 baud. It streams the raw
ADC reading (0..1023) once every ~100 ms as a decimal line, and accepts a
single ASCII byte ('0' or '1') to drive the headlight MOSFET.

We don't auto-toggle the MOSFET on the Nano because we want the threshold
configurable from the HMI. Instead this helper streams readings to a
callback and exposes set_mosfet() for the host control loop.

Run as a standalone tester:
    uv run python -m helpers.ldr_serial --port COM5
"""

import argparse
import threading
import time
from typing import Callable, Optional

import serial


class SerialLDR:
    def __init__(self, port: str, baud: int = 9600,
                 on_value: Optional[Callable[[int], None]] = None):
        self.ser = serial.Serial(port, baud, timeout=0.2)
        time.sleep(2.0)  # Nano resets on open
        self._on_value = on_value
        self._mosfet = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self):
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = self.ser.read(64)
            except (serial.SerialException, OSError):
                break
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    value = int(line)
                except ValueError:
                    continue
                if self._on_value:
                    try:
                        self._on_value(value)
                    except Exception:
                        pass

    def set_mosfet(self, on: bool) -> None:
        if on == self._mosfet:
            return
        self._mosfet = on
        try:
            self.ser.write(b"1" if on else b"0")
            self.ser.flush()
        except (serial.SerialException, OSError):
            pass

    @property
    def mosfet_on(self) -> bool:
        return self._mosfet

    def close(self):
        self._stop.set()
        try:
            self.ser.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=9600)
    args = parser.parse_args()

    last = [0]

    def on_value(v: int):
        last[0] = v

    ldr = SerialLDR(args.port, args.baud, on_value=on_value)
    print("Streaming LDR. Press Ctrl-C to quit.")
    try:
        while True:
            print(f"ldr = {last[0]:4d}  mosfet = {ldr.mosfet_on}")
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        ldr.set_mosfet(False)
        ldr.close()
        print("\nClosed.")


if __name__ == "__main__":
    main()
