"""Demo: mini LIF — TIME_MORNING sensor → LOG_TICK motor + reward.

Run:
  py -3 scripts/demo_lif_mini.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sally_cibote.memory.neuronal import MiniLifBrain, morning_intensity_now  # noqa: E402


def run_window(brain: MiniLifBrain, *, morning: float, steps: int, label: str) -> float:
    brain.stimulate({"TIME_MORNING": morning})
    total = 0.0
    for _ in range(steps):
        brain.step(dt_ms=1.0)
        total += brain.motors()["LOG_TICK"]
    mean = total / max(steps, 1)
    snap = brain.snapshot()
    print(
        f"[{label}] morning={morning:.2f}  "
        f"LOG_TICK_mean={mean:.2f}  "
        f"learned_sf={snap['learned_sf']:+.3f}  "
        f"learned_fm={snap['learned_fm']:+.3f}"
    )
    return mean


def main() -> int:
    brain = MiniLifBrain(seed=7)
    print(f"MiniLifBrain neurons={brain.snapshot()['neuron_count']}")
    print("Sensor: TIME_MORNING | Motor: LOG_TICK | Reward: on_reward(+1/-1)\n")

    night = run_window(brain, morning=0.05, steps=80, label="night")
    morn = run_window(brain, morning=0.95, steps=80, label="morning")

    before = (brain.learned_sf, brain.learned_fm)
    brain.on_reward(+1)
    print(
        f"[reward] +1  learned {before[0]:+.3f}/{before[1]:+.3f} "
        f"→ {brain.learned_sf:+.3f}/{brain.learned_fm:+.3f}"
    )

    morn2 = run_window(brain, morning=0.95, steps=80, label="morning+reward")

    now_i = morning_intensity_now()
    print(f"\nReal local TIME_MORNING intensity ≈ {now_i:.2f}")
    print(f"Check: morning({morn:.2f}) > night({night:.2f}) → {morn > night}")
    print("Learning signal is the learned_* weights (motor may already saturate).")

    out = ROOT / "data" / "memory" / "mini_lif_state.json"
    brain.save(out)
    print(f"Saved weights → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
