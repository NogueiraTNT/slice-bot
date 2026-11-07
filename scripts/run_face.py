"""Abre o rosto da Sally + wake word (sem TTS).

  py -3 -m pip install -e ".[voice]"
  py -3 scripts/run_face.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sally_cibote.ui.face_listen import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
