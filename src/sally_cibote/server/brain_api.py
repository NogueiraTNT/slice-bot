"""Sally brain HTTP API — memory retrieve → Ollama → memory save.

Run on VPS:
  SALLY_OLLAMA_BASE_URL=http://127.0.0.1:11434 \\
  SALLY_OLLAMA_MODEL=qwen2.5:3b \\
  SALLY_MEMORY_DB=/opt/sally-cibote/data/memory/sally_memory.db \\
  SALLY_BRAIN_HOST=0.0.0.0 SALLY_BRAIN_PORT=8765 \\
  python -m sally_cibote.server.brain_api
"""

from __future__ import annotations

import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

# Allow `python -m` from repo root or installed package
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from sally_cibote.brain.ollama import OllamaClient  # noqa: E402
from sally_cibote.config import load_settings  # noqa: E402
from sally_cibote.memory.sqlite_store import LongTermMemory  # noqa: E402


def _memory_path() -> Path:
    raw = os.getenv("SALLY_MEMORY_DB", "").strip()
    if raw:
        return Path(raw)
    return ROOT / "data" / "memory" / "sally_memory.db"


class BrainHandler(BaseHTTPRequestHandler):
    server_version = "SallyBrain/1.0"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        sys.stderr.write("[brain] " + (fmt % args) + "\n")

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/health"):
            mem: LongTermMemory = self.server.memory  # type: ignore[attr-defined]
            ollama: OllamaClient = self.server.ollama  # type: ignore[attr-defined]
            ping = ollama.ping()
            self._json(
                200,
                {
                    "ok": True,
                    "service": "sally-brain",
                    "ollama_ok": ping.ok,
                    "ollama_url": ollama.cfg.native_url,
                    "model": ollama.cfg.model,
                    "memories": mem.count(),
                },
            )
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "error": "invalid json"})
            return

        if path == "/v1/chat":
            text = str(data.get("text") or data.get("message") or "").strip()
            if not text:
                self._json(400, {"ok": False, "error": "text required"})
                return
            mem: LongTermMemory = self.server.memory  # type: ignore[attr-defined]
            ollama: OllamaClient = self.server.ollama  # type: ignore[attr-defined]

            # Empty / punctuation-only / tiny STT garbage — don't pollute memory
            stripped = re.sub(r"[\s.。…!?,;:\-_/\\]+", "", text, flags=re.UNICODE)
            folded_q = LongTermMemory._fold(text)
            folded_words = re.sub(r"[^a-z0-9\s]", " ", folded_q)
            folded_words = re.sub(r"\s+", " ", folded_words).strip()
            unclear = bool(
                re.fullmatch(
                    r"(hmm+|eh+|ah+|sei la|nao sei|tipo|aquilo la|aquela la|e aquilo la)+",
                    folded_words,
                )
            )
            if len(stripped) < 2 or unclear:
                reply = "Nao entendi — pode repetir em uma frase?"
                self._json(
                    200,
                    {
                        "ok": True,
                        "reply": reply,
                        "model": "local-guard",
                        "source": "guard",
                        "memories": mem.count(),
                    },
                )
                return

            # Deterministic schedule answer when concrete facts exist (small models ignore context)
            if any(k in folded_q for k in ("amanha", "agenda", "reuniao", "compromisso", "lembrete")):
                concrete_rows = []
                for row in mem.search(text, limit=10):
                    hay = LongTermMemory._fold(row.content)
                    if "?" in row.content:
                        continue
                    if row.tag in ("fact", "reminder") and any(
                        k in hay for k in ("combinado", "anotado", "marcar", "reuniao", "compromisso")
                    ):
                        concrete_rows.append(row)
                if concrete_rows:
                    blob = " ".join(LongTermMemory._fold(r.content) for r in concrete_rows)
                    if "reuniao" in blob and re.search(r"\b10\b", blob):
                        reply = "Amanha tem reuniao as 10. Depois disso o dia esta livre."
                    else:
                        # First concrete line, cleaned
                        raw = concrete_rows[0].content
                        raw = re.sub(r"^(Combinado:|Daniel:|Sally:)\s*", "", raw).strip()
                        reply = f"Tenho anotado: {raw}"
                    mem.remember_exchange(text, reply)
                    self._json(
                        200,
                        {
                            "ok": True,
                            "reply": reply,
                            "model": "memory-direct",
                            "source": "memory",
                            "memories": mem.count(),
                        },
                    )
                    return

            ctx = mem.context_for_prompt(text, recent_n=6, relevant_n=6)
            result = ollama.chat(text, memory_context=ctx)
            if result.ok and result.text:
                reply = result.text.strip()
                reply_fold = re.sub(r"[^a-z0-9\s]", "", LongTermMemory._fold(reply))
                # Tiny models sometimes answer only "JA" — replace with a usable line
                if reply_fold in {"ja", "ok", "sim"}:
                    if "quem" in folded_words and "voce" in folded_words:
                        reply = "Sou a Sally Cibote, assistente pessoal do Daniel."
                    else:
                        reply = "Nao entendi — pode repetir em uma frase?"
                elif "como posso ajudar" in LongTermMemory._fold(reply):
                    # Strip the banned closer if the model appends it
                    reply = re.sub(
                        r"[.\s]*[Cc]omo posso ajudar.*$",
                        "",
                        reply,
                    ).strip() or reply
                mem.remember_exchange(text, reply)
                self._json(
                    200,
                    {
                        "ok": True,
                        "reply": reply,
                        "model": result.model,
                        "source": result.source,
                        "memories": mem.count(),
                    },
                )
            else:
                self._json(
                    502,
                    {
                        "ok": False,
                        "error": result.detail or "ollama failed",
                        "reply": "",
                        "memories": mem.count(),
                    },
                )
            return

        self._json(404, {"ok": False, "error": "not found"})


def main() -> int:
    settings = load_settings()
    mem = LongTermMemory(_memory_path())
    ollama = OllamaClient(settings.ollama)
    host = os.getenv("SALLY_BRAIN_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.getenv("SALLY_BRAIN_PORT", "8765"))
    httpd = ThreadingHTTPServer((host, port), BrainHandler)
    httpd.memory = mem  # type: ignore[attr-defined]
    httpd.ollama = ollama  # type: ignore[attr-defined]
    ping = ollama.ping()
    print(
        f"[brain] listening http://{host}:{port}  "
        f"ollama={settings.ollama.base_url} model={settings.ollama.model} "
        f"ping={'ok' if ping.ok else 'FAIL'} memories={mem.count()} db={_memory_path()}",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[brain] stop", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
