"""HTTP client for remote Sally brain API (VPS)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class BrainReply:
    ok: bool
    reply: str
    raw: dict
    error: str = ""


def ask_brain(brain_url: str, text: str, *, timeout_s: float = 90.0) -> BrainReply:
    base = (brain_url or "").rstrip("/")
    if not base:
        return BrainReply(False, "", {}, error="SALLY_BRAIN_URL vazio")
    url = f"{base}/v1/chat"
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
            reply = str(data.get("reply") or "").strip()
            ok = bool(data.get("ok", True)) and bool(reply)
            return BrainReply(ok, reply, data, error="" if ok else str(data.get("error") or "empty"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:400]
        return BrainReply(False, "", {}, error=f"HTTP {e.code}: {err}")
    except Exception as e:  # noqa: BLE001
        return BrainReply(False, "", {}, error=str(e))
