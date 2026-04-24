"""
Throttle calibration for the Hobbywing XR10 ESC.

The ESC has a fairly wide deadband around neutral (1500 us) and won't actually
spin the wheels until the pulse is well past it. A short "kickstart" pulse
when leaving neutral overcomes static friction and the BEC dead zone, after
which the ESC will hold a slower target. Forward and reverse have different
deadband edges and different kickstart needs.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Union

PULSE_NEUTRAL = 1500
PULSE_HARD_MIN = 1000
PULSE_HARD_MAX = 2000


@dataclass
class ThrottleCalibration:
    forward_min_us: int = 1580
    forward_max_us: int = 2000
    forward_kick_us: int = 1750
    forward_kick_ms: int = 250
    reverse_min_us: int = 1420
    reverse_max_us: int = 1000
    reverse_kick_us: int = 1300
    reverse_kick_ms: int = 250

    @classmethod
    def from_dict(cls, data: dict) -> "ThrottleCalibration":
        fields = {f for f in cls.__dataclass_fields__}
        return cls(**{k: int(v) for k, v in data.items() if k in fields})

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "ThrottleCalibration":
        p = Path(path)
        if not p.exists():
            return cls()
        return cls.from_dict(json.loads(p.read_text()))

    def save(self, path: Union[str, Path]) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    def percent_to_us(self, percent: float) -> int:
        """Map -100..100 % to a pulse width using the calibrated endpoints.

        |percent| < 1 returns NEUTRAL (no spin).
        Positive: linear from forward_min_us at +1 % to forward_max_us at +100 %.
        Negative: linear from reverse_min_us at -1 % to reverse_max_us at -100 %.
        """
        percent = max(-100.0, min(100.0, float(percent)))
        if abs(percent) < 1.0:
            return PULSE_NEUTRAL
        if percent > 0:
            span = self.forward_max_us - self.forward_min_us
            us = self.forward_min_us + span * (percent - 1.0) / 99.0
        else:
            # reverse_max_us is the *fastest* reverse (closer to 1000),
            # reverse_min_us is the *slowest* reverse (just past 1500).
            span = self.reverse_max_us - self.reverse_min_us
            us = self.reverse_min_us + span * (-percent - 1.0) / 99.0
        return int(round(max(PULSE_HARD_MIN, min(PULSE_HARD_MAX, us))))

    def kick_for(self, percent: float) -> tuple[int, int]:
        """Return (pulse_us, duration_ms) for the kickstart on a transition."""
        if percent > 0:
            return self.forward_kick_us, self.forward_kick_ms
        return self.reverse_kick_us, self.reverse_kick_ms
