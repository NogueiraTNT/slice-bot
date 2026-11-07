"""Configuração via env — Ollama remoto (VPS). Código portátil (sem acoplar a Windows)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")
load_dotenv()


def _strip(url: str | None) -> str:
    return (url or "").strip().rstrip("/")


def _bool(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() not in ("0", "false", "no", "off")


@dataclass(frozen=True)
class OllamaConfig:
    """Endpoint Ollama na VPS. Precedência: SALLY_OLLAMA_BASE_URL > OLLAMA_HOST."""

    base_url: str
    model: str
    timeout_s: float
    api_key: str
    allow_mock: bool

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    @property
    def native_url(self) -> str:
        return self.base_url

    @property
    def openai_compat_url(self) -> str:
        if not self.base_url:
            return ""
        if self.base_url.endswith("/v1"):
            return self.base_url
        return f"{self.base_url}/v1"

    def missing_reason(self) -> str:
        return (
            "SALLY_OLLAMA_BASE_URL / OLLAMA_HOST nao definidos. "
            "Ollama roda na VPS — passe a URL quando houver acesso."
        )


@dataclass(frozen=True)
class VoiceConfig:
    sample_rate: int
    channels: int
    barge_in: bool
    # STT (faster-whisper) — portátil CPU/GPU
    stt_model: str
    stt_device: str
    stt_language: str
    # TTS — edge (neural) default; system = fallback OS
    tts_backend: str
    tts_voice: str
    tts_rate: str  # edge-tts rate, e.g. "+0%" / "-5%"
    tts_system_rate: int  # pyttsx3 words/min


@dataclass(frozen=True)
class LifConfig:
    enabled: bool
    store_path: Path
    stage: str


@dataclass(frozen=True)
class Settings:
    ollama: OllamaConfig
    voice: VoiceConfig
    lif: LifConfig
    project_root: Path


def load_settings() -> Settings:
    base = _strip(os.getenv("SALLY_OLLAMA_BASE_URL")) or _strip(os.getenv("OLLAMA_HOST"))
    if base and "://" not in base:
        base = f"http://{base}"

    ollama = OllamaConfig(
        base_url=base,
        model=os.getenv("SALLY_OLLAMA_MODEL", "llama3.2:1b").strip() or "llama3.2:1b",
        timeout_s=float(os.getenv("SALLY_OLLAMA_TIMEOUT", "90")),
        api_key=os.getenv("SALLY_OLLAMA_API_KEY", "").strip(),
        allow_mock=_bool("SALLY_ALLOW_MOCK", "0"),
    )
    voice = VoiceConfig(
        sample_rate=int(os.getenv("SALLY_SAMPLE_RATE", "16000")),
        channels=int(os.getenv("SALLY_CHANNELS", "1")),
        barge_in=_bool("SALLY_BARGE_IN", "1"),
        stt_model=os.getenv("SALLY_STT_MODEL", "base").strip() or "base",
        stt_device=os.getenv("SALLY_STT_DEVICE", "cpu").strip() or "cpu",
        stt_language=os.getenv("SALLY_STT_LANGUAGE", "pt").strip() or "pt",
        tts_backend=os.getenv("SALLY_TTS_BACKEND", "edge").strip() or "edge",
        tts_voice=os.getenv("SALLY_TTS_VOICE", "pt-BR-FranciscaNeural").strip()
        or "pt-BR-FranciscaNeural",
        tts_rate=os.getenv("SALLY_TTS_RATE", "-5%").strip() or "-5%",
        tts_system_rate=int(os.getenv("SALLY_TTS_SYSTEM_RATE", "165")),
    )
    store = Path(
        os.getenv("SALLY_LIF_PATH", str(_ROOT / "data" / "memory" / "lif.jsonl"))
    )
    lif = LifConfig(
        enabled=_bool("SALLY_LIF_ENABLED", "1"),
        store_path=store,
        stage=os.getenv("SALLY_LIF_STAGE", "newborn").strip() or "newborn",
    )
    return Settings(ollama=ollama, voice=voice, lif=lif, project_root=_ROOT)
