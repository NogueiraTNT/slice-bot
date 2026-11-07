"""CLI Sally Cibote — portátil; cérebro Ollama remoto."""

from __future__ import annotations

import argparse
import json
import sys

from sally_cibote.brain.ollama import OllamaClient
from sally_cibote.config import load_settings
from sally_cibote.voice.pipecat_pipeline import describe_pipeline, try_build_ollama_service
from sally_cibote.voice.session import FullDuplexSession
from sally_cibote.voice.tts import TTSPlayer


def _print_json(data: object) -> None:
    text = json.dumps(data, ensure_ascii=True, indent=2)
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sally-cibote")
    parser.add_argument("--status", action="store_true", help="Status Ollama + pipeline")
    parser.add_argument("--daemon", action="store_true", help="Loop continuo escuta/fala")
    parser.add_argument("--turns", type=int, default=None, help="Max. turnos no daemon")
    parser.add_argument("--listen", type=float, default=5.0, help="Segundos de escuta por turno")
    parser.add_argument("--say", type=str, default=None, help="Fala um texto (teste TTS)")
    args = parser.parse_args(argv)

    settings = load_settings()
    client = OllamaClient(settings.ollama)

    if args.say is not None:
        tts = TTSPlayer(
            backend=settings.voice.tts_backend,
            voice=settings.voice.tts_voice,
            edge_rate=settings.voice.tts_rate,
            system_rate=settings.voice.tts_system_rate,
        )
        ok = tts.speak(args.say, interruptible=True)
        print(f"tts_ok={ok}")
        return 0 if ok else 1

    if args.status:
        ping = client.ping()
        svc = try_build_ollama_service(settings)
        _print_json(
            {
                "ollama_configured": settings.ollama.configured,
                "ollama_base_url": settings.ollama.base_url or None,
                "openai_compat_url": settings.ollama.openai_compat_url or None,
                "model": settings.ollama.model,
                "ping_ok": ping.ok,
                "ping_source": ping.source,
                "ping_detail": ping.detail,
                "pipecat_service": type(svc).__name__ if svc else None,
                "tts_backend": settings.voice.tts_backend,
                "stt_model": settings.voice.stt_model,
                "lif": settings.lif.enabled,
                "pipeline": describe_pipeline(settings),
            }
        )
        return 0 if ping.ok else 1

    if args.daemon:
        session = FullDuplexSession(settings=settings, client=client)
        try:
            session.run_loop(max_turns=args.turns, listen_s=args.listen)
        except KeyboardInterrupt:
            session.stop()
            print("[sally] parado")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
