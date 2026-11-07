"""Captura de microfone (sounddevice) — PC-Daniel."""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Recording:
    samples: np.ndarray  # float32 mono [-1, 1]
    sample_rate: int
    path: Path | None = None

    @property
    def duration_s(self) -> float:
        if self.samples.size == 0:
            return 0.0
        return float(self.samples.shape[0]) / float(self.sample_rate)

    @property
    def rms(self) -> float:
        if self.samples.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(self.samples))))


def list_devices() -> str:
    import sounddevice as sd

    return str(sd.query_devices())


def record_seconds(
    seconds: float = 5.0,
    *,
    sample_rate: int = 16000,
    channels: int = 1,
    out_wav: Path | None = None,
) -> Recording:
    """Grava N segundos do mic padrão."""
    import sounddevice as sd

    frames = int(seconds * sample_rate)
    audio = sd.rec(
        frames,
        samplerate=sample_rate,
        channels=channels,
        dtype="float32",
        blocking=True,
    )
    if channels > 1:
        mono = np.mean(audio, axis=1).astype(np.float32)
    else:
        mono = audio.reshape(-1).astype(np.float32)

    path = None
    if out_wav is not None:
        path = Path(out_wav)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_wav(path, mono, sample_rate)

    return Recording(samples=mono, sample_rate=sample_rate, path=path)


def _write_wav(path: Path, mono: np.ndarray, sample_rate: int) -> None:
    clipped = np.clip(mono, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
