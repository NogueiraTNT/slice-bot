"""Mini LIF brain for Sally — original MIT sketch (not a Pestinha fork).

v1 proactive: time + silence → social → SPEAK_GREET (plus legacy LOG_TICK).
~36 LIF units.
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SENSORY = ("TIME_MORNING", "SILENCE")
INTER = ("FOCUS", "SOCIAL")
MOTORS = ("LOG_TICK", "SPEAK_GREET")

_POOL = {
    "TIME_MORNING": 6,
    "SILENCE": 6,
    "FOCUS": 6,
    "SOCIAL": 6,
    "LOG_TICK": 4,
    "SPEAK_GREET": 8,
}


@dataclass
class _Neuron:
    v: float = 0.0
    refr: float = 0.0
    spikes: int = 0


@dataclass
class MiniLifBrain:
    """Handmade LIF: morning/silence cues → focus/social → motors."""

    seed: int = 7
    tau_ms: float = 20.0
    thresh: float = 1.0
    reset: float = 0.0
    refr_ms: float = 2.0
    # Fixed feedforward + learned deltas
    w_sense_focus: float = 0.55
    w_focus_motor: float = 0.65
    w_silence_social: float = 0.50
    w_morning_social: float = 0.35
    w_social_speak: float = 0.70
    learned_sf: float = 0.0
    learned_fm: float = 0.0
    learned_ss: float = 0.0  # silence→social
    learned_speak: float = 0.0  # social→speak
    learn_rate: float = 0.04
    learn_min: float = -0.2
    learn_max: float = 0.45
    eligibility_decay: float = 0.92
    name_known_boost: float = 0.0  # 0..1 soft prior into SOCIAL
    _rng: random.Random = field(default_factory=random.Random, init=False, repr=False)
    _neurons: dict[str, list[_Neuron]] = field(default_factory=dict, init=False, repr=False)
    _inputs: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _elig_sf: float = field(default=0.0, init=False, repr=False)
    _elig_fm: float = field(default=0.0, init=False, repr=False)
    _elig_ss: float = field(default=0.0, init=False, repr=False)
    _elig_speak: float = field(default=0.0, init=False, repr=False)
    _last_motor_hz: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _sim_ms: float = field(default=0.0, init=False, repr=False)
    _spike_buf: dict[str, int] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng.seed(self.seed)
        self._neurons = {
            name: [_Neuron() for _ in range(_POOL[name])]
            for name in (*SENSORY, *INTER, *MOTORS)
        }
        self._inputs = {name: 0.0 for name in SENSORY}
        self._last_motor_hz = {name: 0.0 for name in MOTORS}
        self._spike_buf = {name: 0 for name in (*SENSORY, *INTER, *MOTORS)}

    def stimulate(self, channels: dict[str, float]) -> None:
        for name, value in channels.items():
            if name in self._inputs:
                self._inputs[name] = max(0.0, min(1.0, float(value)))
            elif name == "NAME_KNOWN":
                self.name_known_boost = max(0.0, min(1.0, float(value)))

    def step(self, dt_ms: float = 1.0) -> None:
        dt_ms = max(0.1, float(dt_ms))
        self._sim_ms += dt_ms
        self._elig_sf *= self.eligibility_decay
        self._elig_fm *= self.eligibility_decay
        self._elig_ss *= self.eligibility_decay
        self._elig_speak *= self.eligibility_decay

        morning = self._drive_sensory("TIME_MORNING", dt_ms)
        silence = self._drive_sensory("SILENCE", dt_ms)

        focus = self._drive_pool(
            "FOCUS",
            external_i=(self.w_sense_focus + self.learned_sf) * morning,
            dt_ms=dt_ms,
        )
        social_i = (
            (self.w_silence_social + self.learned_ss) * silence
            + (self.w_morning_social) * morning
            + 0.25 * self.name_known_boost
        )
        social = self._drive_pool("SOCIAL", external_i=social_i, dt_ms=dt_ms)

        self._drive_pool(
            "LOG_TICK",
            external_i=(self.w_focus_motor + self.learned_fm) * focus,
            dt_ms=dt_ms,
        )
        self._drive_pool(
            "SPEAK_GREET",
            external_i=(self.w_social_speak + self.learned_speak) * social,
            dt_ms=dt_ms,
        )

        self._elig_sf = min(1.0, self._elig_sf + morning * focus * 0.15)
        self._elig_fm = min(1.0, self._elig_fm + focus * self._pool_rate("LOG_TICK") * 0.15)
        self._elig_ss = min(1.0, self._elig_ss + silence * social * 0.15)
        self._elig_speak = min(
            1.0, self._elig_speak + social * self._pool_rate("SPEAK_GREET") * 0.15
        )

        self._publish_motor_hz(dt_ms)
        self._clear_spikes()

    def motors(self) -> dict[str, float]:
        return dict(self._last_motor_hz)

    def on_reward(self, sign: int) -> None:
        """+1 strengthens active pathways; -1 weakens them."""
        s = 1.0 if sign >= 0 else -1.0
        self.learned_sf = self._clip(
            self.learned_sf + s * self.learn_rate * (0.2 + self._elig_sf)
        )
        self.learned_fm = self._clip(
            self.learned_fm + s * self.learn_rate * (0.2 + self._elig_fm)
        )
        self.learned_ss = self._clip(
            self.learned_ss + s * self.learn_rate * (0.25 + self._elig_ss)
        )
        self.learned_speak = self._clip(
            self.learned_speak + s * self.learn_rate * (0.25 + self._elig_speak)
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "sim_ms": self._sim_ms,
            "inputs": dict(self._inputs),
            "motors_hz": self.motors(),
            "learned_sf": self.learned_sf,
            "learned_fm": self.learned_fm,
            "learned_ss": self.learned_ss,
            "learned_speak": self.learned_speak,
            "name_known_boost": self.name_known_boost,
            "neuron_count": sum(len(v) for v in self._neurons.values()),
        }

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "seed": self.seed,
            "learned_sf": self.learned_sf,
            "learned_fm": self.learned_fm,
            "learned_ss": self.learned_ss,
            "learned_speak": self.learned_speak,
            "saved_at": time.time(),
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self, path: Path | str) -> None:
        path = Path(path)
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self.learned_sf = float(data.get("learned_sf", 0.0))
        self.learned_fm = float(data.get("learned_fm", 0.0))
        self.learned_ss = float(data.get("learned_ss", 0.0))
        self.learned_speak = float(data.get("learned_speak", 0.0))

    def _clip(self, w: float) -> float:
        return max(self.learn_min, min(self.learn_max, w))

    def _drive_sensory(self, name: str, dt_ms: float) -> float:
        intensity = self._inputs.get(name, 0.0)
        return self._drive_pool(name, external_i=1.8 * intensity, dt_ms=dt_ms)

    def _pool_rate(self, name: str) -> float:
        neurons = self._neurons[name]
        spikes = sum(n.spikes for n in neurons)
        return min(1.5, spikes / max(len(neurons), 1))

    def _drive_pool(self, name: str, *, external_i: float, dt_ms: float) -> float:
        neurons = self._neurons[name]
        spikes = 0
        for n in neurons:
            if n.refr > 0:
                n.refr = max(0.0, n.refr - dt_ms)
                continue
            noise = self._rng.uniform(-0.05, 0.05)
            n.v += dt_ms * ((-n.v / self.tau_ms) + external_i + noise)
            if n.v >= self.thresh:
                n.v = self.reset
                n.refr = self.refr_ms
                n.spikes += 1
                spikes += 1
        return min(1.5, spikes / max(len(neurons), 1))

    def _publish_motor_hz(self, dt_ms: float) -> None:
        for name in MOTORS:
            neurons = self._neurons[name]
            spikes = sum(n.spikes for n in neurons)
            hz = (spikes / max(dt_ms, 1e-6)) * 1000.0 / max(len(neurons), 1)
            self._last_motor_hz[name] = hz

    def _clear_spikes(self) -> None:
        for pool in self._neurons.values():
            for n in pool:
                n.spikes = 0


def morning_intensity_now(*, hour: int | None = None) -> float:
    """Map local hour → TIME_MORNING intensity (peak ~8–10)."""
    if hour is None:
        hour = time.localtime().tm_hour
    return max(0.0, math.exp(-0.5 * ((hour - 9) / 2.5) ** 2))


def silence_intensity(silence_s: float, *, threshold_s: float = 90.0) -> float:
    """Map quiet time → SILENCE channel 0..1 (ramps after threshold)."""
    if silence_s <= 0:
        return 0.0
    # Soft ramp: starts rising near 50% of threshold, saturates ~2×
    x = silence_s / max(threshold_s, 1.0)
    return max(0.0, min(1.0, (x - 0.4) / 0.8))
