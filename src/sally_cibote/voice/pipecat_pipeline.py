"""Pipecat: OLLamaLLMService remoto + Whisper STT + interrupções.

Transport LocalAudio (pyaudio) é opcional — se faltar, use FullDuplexSession
(sounddevice), que é o caminho portátil padrão.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from sally_cibote.config import Settings


@dataclass(frozen=True)
class PipecatOllamaSpec:
    openai_compat_base_url: str
    model: str
    api_key: str
    barge_in: bool
    configured: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "service": "OLLamaLLMService",
            "base_url": self.openai_compat_base_url,
            "model": self.model,
            "api_key_set": bool(self.api_key),
            "barge_in": self.barge_in,
            "configured": self.configured,
            "notes": "InterruptionFrame; sem wake word; Ollama na VPS.",
        }


def build_ollama_spec(settings: Settings) -> PipecatOllamaSpec:
    o = settings.ollama
    return PipecatOllamaSpec(
        openai_compat_base_url=o.openai_compat_url,
        model=o.model,
        api_key=o.api_key or "ollama",
        barge_in=settings.voice.barge_in,
        configured=o.configured,
    )


def try_build_ollama_service(settings: Settings) -> Any | None:
    spec = build_ollama_spec(settings)
    if not spec.configured:
        return None
    try:
        from pipecat.services.ollama.llm import OLLamaLLMService
    except ImportError:
        return None
    try:
        return OLLamaLLMService(
            base_url=spec.openai_compat_base_url,
            api_key=spec.api_key,
            settings=OLLamaLLMService.Settings(model=spec.model),
        )
    except Exception:  # noqa: BLE001
        return OLLamaLLMService(model=spec.model, base_url=spec.openai_compat_base_url, api_key=spec.api_key)


def describe_pipeline(settings: Settings) -> dict[str, Any]:
    spec = build_ollama_spec(settings)
    return {
        "transport": "sounddevice (portatil) / LocalAudio opcional",
        "vad": "energia RMS + Silero quando Pipecat local",
        "stt": f"faster-whisper:{settings.voice.stt_model}",
        "llm": spec.as_dict(),
        "tts": f"{settings.voice.tts_backend}:{settings.voice.tts_voice}",
        "interruption": True,
        "wake_word": False,
        "lif": settings.lif.enabled,
        "n8n": False,
        "whatsapp": False,
        "portable": True,
    }


async def run_pipecat_local_if_available(settings: Settings) -> bool:
    """Tenta pipeline Pipecat completo. Retorna False se deps locais faltarem."""
    if not settings.ollama.configured:
        return False
    try:
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask
        from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
        from pipecat.services.whisper.stt import WhisperSTTService
        from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams
    except ImportError as exc:
        print(f"[pipecat] deps locais indisponiveis ({exc}); use --daemon (sounddevice)")
        return False

    llm = try_build_ollama_service(settings)
    if llm is None:
        return False

    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        )
    )
    stt = WhisperSTTService()
    context = OpenAILLMContext(
        messages=[
            {
                "role": "system",
                "content": (
                    "Voce e a Sally Cibote. Fale em portugues do Brasil, "
                    "curto e natural (1-2 frases)."
                ),
            }
        ]
    )
    context_aggregator = llm.create_context_aggregator(context)

    # TTS: Pipecat precisa de um serviço TTS — sem Piper/cloud, saímos
    # e deixamos o loop sounddevice+edge-tts (mais portátil/humanizado).
    print("[pipecat] LocalAudio+Whisper+Ollama ok; TTS neural fica no loop portatil (edge).")
    print("[pipecat] Prefira: python -m sally_cibote --daemon")
    _ = (transport, stt, context_aggregator, Pipeline, PipelineRunner, PipelineParams, PipelineTask)
    return False


def run_pipecat_local_if_available_sync(settings: Settings) -> bool:
    return asyncio.run(run_pipecat_local_if_available(settings))
