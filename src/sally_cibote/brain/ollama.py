"""Cliente HTTP para Ollama remoto (VPS). Respostas curtas e faláveis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from sally_cibote.config import OllamaConfig

SALLY_SYSTEM = (
    "Voce e a Sally Cibote, assistente de voz amiga em portugues do Brasil. "
    "Fale como gente: calorosa, clara, natural — nao robotica. "
    "Respostas CURTAS (1 a 2 frases), faceis de ouvir em voz alta. "
    "Evite listas, markdown, emojis e codigo. "
    "Se nao souber, diga com leveza. Nunca mencione que e um modelo de linguagem."
)


@dataclass
class OllamaReply:
    text: str
    source: str  # "vps" | "mock"
    model: str
    ok: bool
    detail: str = ""


class OllamaClient:
    def __init__(self, cfg: OllamaConfig) -> None:
        self.cfg = cfg

    def ping(self) -> OllamaReply:
        if not self.cfg.configured:
            if self.cfg.allow_mock:
                return OllamaReply("", "mock", self.cfg.model, True, self.cfg.missing_reason())
            return OllamaReply("", "vps", self.cfg.model, False, self.cfg.missing_reason())
        url = f"{self.cfg.native_url}/api/tags"
        try:
            with httpx.Client(timeout=self.cfg.timeout_s) as client:
                r = client.get(url, headers=self._headers())
                r.raise_for_status()
            return OllamaReply("", "vps", self.cfg.model, True, f"tags ok ({url})")
        except Exception as exc:  # noqa: BLE001
            return OllamaReply("", "vps", self.cfg.model, False, f"{type(exc).__name__}: {exc}")

    def chat(self, user_text: str, *, memory_context: str = "") -> OllamaReply:
        if not self.cfg.configured:
            if self.cfg.allow_mock:
                return OllamaReply(
                    "Oi! Sou a Sally em modo mock — a VPS ainda nao respondeu. "
                    "Quando o Daniel liberar, eu penso de verdade.",
                    "mock",
                    self.cfg.model,
                    True,
                    self.cfg.missing_reason(),
                )
            return OllamaReply("", "vps", self.cfg.model, False, self.cfg.missing_reason())

        system = SALLY_SYSTEM
        if memory_context:
            system = system + "\n\nContexto recente:\n" + memory_context

        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 120,
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
        }
        url = f"{self.cfg.native_url}/api/chat"
        try:
            with httpx.Client(timeout=self.cfg.timeout_s) as client:
                r = client.post(url, json=payload, headers=self._headers())
                r.raise_for_status()
                data = r.json()
            text = (
                (data.get("message") or {}).get("content") or data.get("response") or ""
            ).strip()
            if not text:
                text = json.dumps(data, ensure_ascii=False)[:400]
            # Limpa artefatos nao faláveis
            for junk in ("```", "**", "##", "- "):
                text = text.replace(junk, "")
            return OllamaReply(text, "vps", data.get("model") or self.cfg.model, True, url)
        except Exception as exc:  # noqa: BLE001
            if self.cfg.allow_mock:
                return OllamaReply(
                    f"Nao consegui falar com a VPS agora ({type(exc).__name__}). "
                    "Mas o caminho de voz no dispositivo esta ok.",
                    "mock",
                    self.cfg.model,
                    True,
                    str(exc),
                )
            return OllamaReply("", "vps", self.cfg.model, False, f"{type(exc).__name__}: {exc}")

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            h["Authorization"] = f"Bearer {self.cfg.api_key}"
        return h
