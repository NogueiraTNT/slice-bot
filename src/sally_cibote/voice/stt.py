"""STT portátil via faster-whisper (CPU/GPU). Sem APIs cloud obrigatórias."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class WhisperSTT:
    """Transcreve float32 mono [-1,1] → texto.

    Modelo default `base` (leve). Para wake, preferir `small` se baixado.
    """

    model_size: str = "base"
    device: str = "cpu"
    language: str = "pt"
    # Silence gate — wake words are short/quiet; keep this low.
    min_rms: float = 0.0006
    _model: object | None = field(default=None, init=False, repr=False)

    def _ensure(self) -> object:
        if self._model is None:
            from faster_whisper import WhisperModel

            compute = "int8" if self.device == "cpu" else "float16"
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=compute,
            )
        return self._model

    def transcribe(
        self,
        samples: np.ndarray,
        sample_rate: int,
        *,
        initial_prompt: str | None = None,
        vad_filter: bool = True,
        beam_size: int = 1,
        min_rms: float | None = None,
    ) -> str:
        if samples.size == 0:
            return ""
        audio = samples.astype(np.float32).reshape(-1)
        rms = float(np.sqrt(np.mean(np.square(audio))))
        gate = self.min_rms if min_rms is None else min_rms
        if rms < gate:
            return ""

        model = self._ensure()
        # faster-whisper espera 16 kHz
        if sample_rate != 16000:
            duration = audio.shape[0] / float(sample_rate)
            target = max(1, int(duration * 16000))
            # resample linear simples (portátil, sem librosa)
            x_old = np.linspace(0.0, 1.0, num=audio.shape[0], endpoint=False)
            x_new = np.linspace(0.0, 1.0, num=target, endpoint=False)
            audio = np.interp(x_new, x_old, audio).astype(np.float32)

        kwargs: dict = {
            "language": self.language,
            "vad_filter": vad_filter,
            "beam_size": beam_size,
        }
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt

        segments, _info = model.transcribe(audio, **kwargs)
        parts = [seg.text.strip() for seg in segments if seg.text and seg.text.strip()]
        return " ".join(parts).strip()
