"""Minimal n8n webhook client for Sally face / voice commands."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class N8nReply:
    ok: bool
    reply: str
    raw: dict
    error: str = ""


def ask_n8n(webhook_url: str, text: str, *, timeout_s: float = 45.0) -> N8nReply:
    """POST `{text}` to an n8n webhook; expect JSON `{reply: ...}`."""
    url = (webhook_url or "").strip()
    if not url:
        return N8nReply(False, "", {}, error="SALLY_N8N_WEBHOOK_URL vazio")
    payload = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body else {}
            if not isinstance(data, dict):
                data = {"reply": str(data)}
            reply = str(data.get("reply") or data.get("message") or data.get("text") or "").strip()
            if not reply:
                reply = body[:200] if body else "(resposta vazia do n8n)"
            return N8nReply(True, reply, data)
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:400]
        return N8nReply(False, "", {}, error=f"HTTP {e.code}: {err}")
    except Exception as e:  # noqa: BLE001 — surface to face log
        return N8nReply(False, "", {}, error=str(e))
