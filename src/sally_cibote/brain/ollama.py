"""Cliente HTTP para Ollama (local ou VPS). Respostas curtas e diretas."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from sally_cibote.config import OllamaConfig

# Personalidade — responde direto; memória vem injetada no contexto.
SALLY_SYSTEM = """\
Voce e a Sally Cibote, assistente pessoal do Daniel.
Fale em portugues do Brasil, tom falado, caloroso e direto.

Comportamento:
- Responda JA ao pedido com 1 ou 2 frases curtas e concretas.
- NAO comece com "em que posso ajudar", "como posso ajudar", "o que voce precisa" nem cumprimentos longos.
- Nunca diga "vamos verificar" nem "ja volto" — responda com o que sabe agora.
- Hora e data: use EXATAMENTE o dia/hora do "Contexto atual". Nao invente o dia da semana.
- Agenda / amanha / reuniao: priorize linhas [fact]/[reminder] com "Combinado", "Anotado" ou "marcar". Ignore perguntas antigas do Daniel e respostas "nada marcado" se houver um combinado concreto (ex.: reuniao as 10). So diga "nada marcado" se nao houver nenhum compromisso concreto nas Memorias.
- Prefira tags [fact] e [reminder] sobre conversas recentes confusas ou respostas antigas erradas.
- Entrada vaga, confusa ou sem sentido: peca para repetir em uma frase curta. Nao invente identidade, agenda nem assunto. Nao responda so "JA".
- So faca UMA pergunta se faltar um dado imprescindivel.
- Sem listas, markdown, emojis, codigo, hashtags ou ingles.
- Nunca diga que e um modelo de linguagem, IA ou chatbot.
"""


def _runtime_context() -> str:
    """Contexto leve injetado a cada turno: horario local + agenda opcional."""
    try:
        now = datetime.now(ZoneInfo("America/Sao_Paulo"))
    except Exception:  # noqa: BLE001
        now = datetime.now()
    weekday = (
        "segunda",
        "terca",
        "quarta",
        "quinta",
        "sexta",
        "sabado",
        "domingo",
    )[now.weekday()]
    lines = [
        f"Agora: {weekday}, {now.strftime('%d/%m/%Y %H:%M')} (America/Sao_Paulo).",
        "Usuario: Daniel.",
    ]
    agenda = (os.getenv("SALLY_AGENDA_NOTE") or "").strip()
    if agenda:
        lines.append(f"Agenda de hoje (resumo): {agenda}")
    else:
        lines.append(
            "Agenda: use as Memorias ([fact]/[reminder]/Combinado/Anotado). "
            "Nao invente compromissos que nao estejam la."
        )
    return "\n".join(lines)


@dataclass
class OllamaReply:
    text: str
    source: str  # "local" | "vps" | "mock"
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
            return OllamaReply("", "local", self.cfg.model, False, self.cfg.missing_reason())
        url = f"{self.cfg.native_url}/api/tags"
        try:
            with httpx.Client(timeout=self.cfg.timeout_s) as client:
                r = client.get(url, headers=self._headers())
                r.raise_for_status()
            src = "local" if "localhost" in self.cfg.native_url or "127.0.0.1" in self.cfg.native_url else "vps"
            return OllamaReply("", src, self.cfg.model, True, f"tags ok ({url})")
        except Exception as exc:  # noqa: BLE001
            return OllamaReply("", "local", self.cfg.model, False, f"{type(exc).__name__}: {exc}")

    def chat(self, user_text: str, *, memory_context: str = "") -> OllamaReply:
        if not self.cfg.configured:
            if self.cfg.allow_mock:
                return OllamaReply(
                    "Oi Daniel — estou em modo mock sem Ollama.",
                    "mock",
                    self.cfg.model,
                    True,
                    self.cfg.missing_reason(),
                )
            return OllamaReply("", "local", self.cfg.model, False, self.cfg.missing_reason())

        system = SALLY_SYSTEM + "\n\nContexto atual:\n" + _runtime_context()
        if memory_context:
            system = (
                system
                + "\n\nMemorias (use se forem uteis; ignore o que nao couber):\n"
                + memory_context
            )

        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "stream": False,
            "options": {
                "temperature": 0.4,
                "top_p": 0.9,
                "num_predict": 120,
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
        }
        url = f"{self.cfg.native_url}/api/chat"
        src = "local" if "localhost" in self.cfg.native_url or "127.0.0.1" in self.cfg.native_url else "vps"
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
            for junk in ("```", "**", "##", "- ", "* ", "#"):
                text = text.replace(junk, "")
            text = " ".join(text.split())
            return OllamaReply(text, src, data.get("model") or self.cfg.model, True, url)
        except Exception as exc:  # noqa: BLE001
            if self.cfg.allow_mock:
                return OllamaReply(
                    f"Nao consegui falar com o Ollama ({type(exc).__name__}).",
                    "mock",
                    self.cfg.model,
                    True,
                    str(exc),
                )
            return OllamaReply("", src, self.cfg.model, False, f"{type(exc).__name__}: {exc}")

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            h["Authorization"] = f"Bearer {self.cfg.api_key}"
        return h
