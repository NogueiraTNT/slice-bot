"""Loop mic → STT real → Ollama → TTS humanizado, com barge-in.

Audio I/O via sounddevice (portátil). Sem wake word.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import numpy as np

from sally_cibote.brain.ollama import OllamaClient
from sally_cibote.config import Settings
from sally_cibote.memory.lif import LifMemory
from sally_cibote.voice.stt import WhisperSTT
from sally_cibote.voice.tts import TTSPlayer
from sally_cibote.voice.vad import is_speech


@dataclass
class FullDuplexSession:
    settings: Settings
    client: OllamaClient
    tts: TTSPlayer | None = None
    stt: WhisperSTT | None = None
    lif: LifMemory | None = None
    _stop: threading.Event = field(default_factory=threading.Event, init=False)
    interruptions: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        v = self.settings.voice
        if self.tts is None:
            self.tts = TTSPlayer(
                backend=v.tts_backend,
                voice=v.tts_voice,
                edge_rate=v.tts_rate,
                system_rate=v.tts_system_rate,
            )
        if self.stt is None:
            self.stt = WhisperSTT(
                model_size=v.stt_model,
                device=v.stt_device,
                language=v.stt_language,
            )
        if self.lif is None and self.settings.lif.enabled:
            self.lif = LifMemory(
                path=self.settings.lif.store_path,
                stage=self.settings.lif.stage,
            )

    def stop(self) -> None:
        self._stop.set()
        if self.tts:
            self.tts.interrupt()

    def run_turn(self, user_text: str) -> str:
        assert self.tts is not None
        ctx = self.lif.context_snippet() if self.lif else ""
        reply = self.client.chat(user_text, memory_context=ctx)
        if not reply.ok:
            raise RuntimeError(reply.detail)
        watcher = threading.Thread(target=self._barge_in_watch, daemon=True)
        watcher.start()
        self.tts.speak(reply.text, interruptible=self.settings.voice.barge_in)
        if self.lif:
            self.lif.remember_turn(user_text, reply.text)
        return reply.text

    def run_loop(self, *, max_turns: int | None = None, listen_s: float = 5.0) -> None:
        """Loop contínuo: grava → Whisper STT → Ollama → TTS, com barge-in."""
        from sally_cibote.voice.capture import record_seconds

        assert self.stt is not None and self.tts is not None
        turns = 0
        sr = self.settings.voice.sample_rate
        ch = self.settings.voice.channels
        print("[sally] carregando STT (primeiro uso pode baixar o modelo)...")
        # Warmup leve
        _ = self.stt.transcribe(np.zeros(1600, dtype=np.float32), 16000)

        while not self._stop.is_set():
            if max_turns is not None and turns >= max_turns:
                break
            print(f"[sally] escutando {listen_s:.0f}s...")
            rec = record_seconds(listen_s, sample_rate=sr, channels=ch)
            text = self.stt.transcribe(rec.samples, rec.sample_rate)
            print(f"[sally] STT: {text!r} (rms={rec.rms:.4f})")
            if not text:
                print("[sally] silencio / sem fala — continuo ouvindo")
                continue
            # LIF: confirmações simples por voz
            low = text.lower()
            if self.lif and any(w in low for w in ("confirma", "pode sim", "pode fazer", "ok sally")):
                stage = self.lif.confirm()
                msg = f"Combinado. Estou no estagio {stage}."
                self.tts.speak(msg, interruptible=True)
                continue
            if self.lif and any(w in low for w in ("cancela", "nao faz", "não faz", "rejeita")):
                stage = self.lif.reject()
                self.tts.speak(f"Tudo bem, cancelei. Continuo no estagio {stage}.", interruptible=True)
                continue

            ctx = self.lif.context_snippet() if self.lif else ""
            reply = self.client.chat(text, memory_context=ctx)
            print(f"[sally] ({reply.source}) {reply.text}")
            if not reply.ok:
                print(f"[sally] erro LLM: {reply.detail}")
                continue
            watcher = threading.Thread(target=self._barge_in_watch, daemon=True)
            watcher.start()
            completed = self.tts.speak(reply.text, interruptible=self.settings.voice.barge_in)
            if not completed:
                self.interruptions += 1
                print("[sally] barge-in: TTS interrompido")
            if self.lif:
                self.lif.remember_turn(text, reply.text)
            turns += 1

    def _barge_in_watch(self) -> None:
        if not self.settings.voice.barge_in or self.tts is None:
            return
        try:
            import sounddevice as sd
        except ImportError:
            return
        sr = self.settings.voice.sample_rate
        block = int(0.05 * sr)
        # Ignora eco inicial do próprio TTS
        time.sleep(0.35)
        stream = sd.InputStream(samplerate=sr, channels=1, dtype="float32", blocksize=block)
        stream.start()
        try:
            while not self._stop.is_set() and self.tts.speaking:
                data, _ = stream.read(block)
                if is_speech(data.reshape(-1), threshold=0.035):
                    self.tts.interrupt()
                    break
                time.sleep(0.01)
        finally:
            stream.stop()
            stream.close()
