#!/usr/bin/env python3
"""Teste: grava ~5s → Whisper STT → Ollama VPS → TTS humanizado."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sally_cibote.brain.ollama import OllamaClient
from sally_cibote.config import load_settings
from sally_cibote.memory.lif import LifMemory
from sally_cibote.voice.pipecat_pipeline import build_ollama_spec, describe_pipeline
from sally_cibote.voice.stt import WhisperSTT
from sally_cibote.voice.tts import TTSPlayer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--no-mic", action="store_true")
    parser.add_argument("--no-tts", action="store_true")
    parser.add_argument(
        "--text",
        default="Oi Sally, tudo bem? Me responde bem curtinho, como amiga.",
    )
    parser.add_argument("--wav", type=Path, default=ROOT / "data" / "ui" / "test_5s.wav")
    args = parser.parse_args()

    settings = load_settings()
    client = OllamaClient(settings.ollama)
    lif = LifMemory(path=settings.lif.store_path, stage=settings.lif.stage) if settings.lif.enabled else None

    report: dict = {
        "ollama_base_url": settings.ollama.base_url,
        "model": settings.ollama.model,
        "pipecat_spec": build_ollama_spec(settings).as_dict(),
        "pipeline": describe_pipeline(settings),
    }

    ping = client.ping()
    report["ping"] = {"ok": ping.ok, "source": ping.source, "detail": ping.detail}
    print(f"[ping] ok={ping.ok} source={ping.source}")

    user_text = args.text
    if not args.no_mic:
        from sally_cibote.voice.capture import record_seconds

        print(f"[mic] gravando {args.seconds:.1f}s...")
        rec = record_seconds(
            args.seconds,
            sample_rate=settings.voice.sample_rate,
            channels=settings.voice.channels,
            out_wav=args.wav,
        )
        report["wav"] = str(rec.path)
        report["rms"] = rec.rms
        print(f"[mic] rms={rec.rms:.4f} wav={rec.path}")
        stt = WhisperSTT(
            model_size=settings.voice.stt_model,
            device=settings.voice.stt_device,
            language=settings.voice.stt_language,
        )
        print("[stt] transcrevendo (whisper)...")
        user_text = stt.transcribe(rec.samples, rec.sample_rate) or args.text
        report["stt"] = user_text
        print(f"[stt] {user_text!r}")

    ctx = lif.context_snippet() if lif else ""
    reply = client.chat(user_text, memory_context=ctx)
    report["reply"] = {
        "ok": reply.ok,
        "source": reply.source,
        "text": reply.text,
        "detail": reply.detail,
    }
    print(f"[llm] {reply.text}")

    if reply.ok and lif:
        lif.remember_turn(user_text, reply.text)

    if reply.ok and not args.no_tts and reply.text:
        tts = TTSPlayer(
            backend=settings.voice.tts_backend,
            voice=settings.voice.tts_voice,
            edge_rate=settings.voice.tts_rate,
            system_rate=settings.voice.tts_system_rate,
        )
        completed = tts.speak(reply.text, interruptible=True)
        report["tts"] = {"ok": True, "completed": completed, "backend": settings.voice.tts_backend}
        print(f"[tts] completed={completed} backend={settings.voice.tts_backend}")
    else:
        report["tts"] = {"skipped": True}

    out = ROOT / "data" / "ui" / "test_voice_5s_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[report] {out}")
    return 0 if reply.ok and reply.source == "vps" else (1 if reply.ok else 2)


if __name__ == "__main__":
    raise SystemExit(main())
