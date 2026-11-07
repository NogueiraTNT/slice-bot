"""VAD simples por energia (RMS) — suficiente para barge-in básico no desktop."""

from __future__ import annotations

import numpy as np


def rms(frame: np.ndarray) -> float:
    if frame.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(frame.astype(np.float32)))))


def is_speech(frame: np.ndarray, *, threshold: float = 0.02) -> bool:
    """True se o frame parece ter fala (energia acima do limiar)."""
    return rms(frame) >= threshold
