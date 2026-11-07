"""TTS portátil — neural (edge-tts) com fallback de sistema.

Sem acoplar a Windows: edge-tts + playback via sounddevice/mp3 decoder quando possível;
fallback opcional via pyttsx3 se o SO tiver voz.
Barge-in: interrupt() para playback imediato.
"""

from __future__ import annotations

import asyncio
import io
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path


def _humanize_text(text: str) -> str:
    """Pequenos ajustes pra fala mais natural (pausas curtas)."""
    t = " ".join((text or "").strip().split())
    if not t:
        return t
    # Evita rajadas: quebra em frases curtas com reticências leves
    for sep in (". ", "! ", "? ", "; "):
        if sep in t:
            parts = [p.strip() for p in t.replace("!", ".").replace("?", ".").split(".") if p.strip()]
            if len(parts) > 1:
                return ". ".join(parts[:3]) + "."
            break
    return t


@dataclass
class TTSPlayer:
    """Fala texto. Backend: edge (default) | system | stub | muted."""

    backend: str = "edge"
    voice: str = "pt-BR-FranciscaNeural"
    edge_rate: str = "-5%"
    system_rate: int = 165
    enabled: bool = True
    _speaking: bool = field(default=False, init=False)
    _cancel: threading.Event = field(default_factory=threading.Event, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _system_engine: object | None = field(default=None, init=False, repr=False)
    _pygame_ready: bool = field(default=False, init=False)

    @property
    def speaking(self) -> bool:
        return self._speaking

    def speak(self, text: str, *, interruptible: bool = True) -> bool:
        text = _humanize_text(text)
        if not text:
            return True
        if not self.enabled or self.backend in ("off", "mute", "muted", "none"):
            print(f"[tts] muted: {text}", flush=True)
            return True
        with self._lock:
            self._cancel.clear()
            self._speaking = True
            try:
                if self.backend == "stub":
                    print(self.speak_stub(text))
                    return True
                if self.backend == "system":
                    return self._speak_system(text, interruptible=interruptible)
                # edge first, fallback system
                try:
                    return self._speak_edge(text, interruptible=interruptible)
                except Exception as exc:  # noqa: BLE001
                    print(f"[tts] edge falhou ({type(exc).__name__}), fallback system")
                    return self._speak_system(text, interruptible=interruptible)
            finally:
                self._speaking = False

    def interrupt(self) -> None:
        self._cancel.set()
        self._speaking = False
        try:
            import pygame

            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:  # noqa: BLE001
            pass
        if self._system_engine is not None:
            try:
                self._system_engine.stop()
            except Exception:  # noqa: BLE001
                pass

    def speak_stub(self, text: str) -> str:
        return f"[TTS stub] {text}"

    # --- edge-tts (neural, cross-platform) ---

    def _speak_edge(self, text: str, *, interruptible: bool) -> bool:
        import edge_tts

        async def _synth() -> bytes:
            communicate = edge_tts.Communicate(text, self.voice, rate=self.edge_rate)
            buf = io.BytesIO()
            async for chunk in communicate.stream():
                if self._cancel.is_set():
                    break
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            return buf.getvalue()

        audio = asyncio.run(_synth())
        if self._cancel.is_set() or not audio:
            return False
        return self._play_mp3_bytes(audio, interruptible=interruptible)

    def _play_mp3_bytes(self, data: bytes, *, interruptible: bool) -> bool:
        import pygame

        if not self._pygame_ready:
            pygame.mixer.init()
            self._pygame_ready = True
        path = Path(tempfile.gettempdir()) / "sally_tts.mp3"
        path.write_bytes(data)
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if interruptible and self._cancel.is_set():
                pygame.mixer.music.stop()
                return False
            pygame.time.wait(40)
        return not self._cancel.is_set()

    # --- system TTS (opcional; Windows SAPI / espeak etc.) ---

    def _speak_system(self, text: str, *, interruptible: bool) -> bool:
        import pyttsx3

        if self._system_engine is None:
            eng = pyttsx3.init()
            eng.setProperty("rate", self.system_rate)
            try:
                for v in eng.getProperty("voices"):
                    name = (getattr(v, "name", "") or "").lower()
                    if "pt" in name or "maria" in name or "brazil" in name:
                        eng.setProperty("voice", v.id)
                        break
            except Exception:  # noqa: BLE001
                pass
            self._system_engine = eng
        engine = self._system_engine
        try:
            engine.stop()
        except Exception:  # noqa: BLE001
            pass
        engine.say(text)
        done = threading.Event()

        def _run() -> None:
            try:
                engine.runAndWait()
            finally:
                done.set()

        threading.Thread(target=_run, daemon=True).start()
        while not done.wait(0.05):
            if interruptible and self._cancel.is_set():
                try:
                    engine.stop()
                except Exception:  # noqa: BLE001
                    pass
                return False
        return not self._cancel.is_set()
