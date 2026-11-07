"""Demo proactive LIF without mic.

  py -3 scripts/demo_proactive.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sally_cibote.memory.proactive import ProactiveController  # noqa: E402


def main() -> int:
    ctl = ProactiveController(
        root=ROOT,
        stage="newborn",
        silence_threshold_s=10.0,
        cooldown_s=2.0,
        speak_hz_threshold=8.0,
    )
    ctl.note_user_text("Oi, meu nome é Daniel")
    print("learned name:", ctl.episodic.user_name)
    ctl.episodic.last_interaction_ts = time.time() - 120
    ctl.episodic.save()

    for i in range(6):
        prop = ctl.tick(steps=80)
        print(f"tick {i}: {prop}")
        if prop:
            print("OK — proactive text:", prop.text)
            print("reason:", prop.reason)
            return 0
    print("FAIL — no proactive fire (try lowering SALLY_PROACTIVE_HZ)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
