"""Face UI + Slice wake + active conversation session (text only, no TTS).

After wake, Sally stays in session: more speech needs no new Slice until
silence timeout or a goodbye phrase ("tchau", "Slice tchau", …).
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np

from sally_cibote.brain.ollama import OllamaClient
from sally_cibote.config import load_settings
from sally_cibote.hands.brain_client import ask_brain
from sally_cibote.memory.proactive import ProactiveController
from sally_cibote.memory.sqlite_store import LongTermMemory
from sally_cibote.ui.face import FaceApp, FaceExpression
from sally_cibote.voice.capture import record_seconds
from sally_cibote.voice.session_end import is_session_end
from sally_cibote.voice.stt import WhisperSTT
from sally_cibote.voice.vad import is_speech, rms
from sally_cibote.voice.wake import normalize_pt, score_wake, strip_wake_prefix

# Stage-1 energy gate (mic is quiet: silence ~0.001, speech ~0.015+)
_SPEECH_RMS = 0.0035
_CHUNK_S = 0.45
_ROLL_S = 2.8
_POST_SPEECH_CHUNKS = 2
_WAKE_PROMPT = "Slice. Olá Slice. É lice. Aslice."
_WAKE_COOLDOWN_S = 0.35
_SESSION_SILENCE_S = float(os.getenv("SALLY_SESSION_SILENCE_S", "45"))


def _log(msg: str) -> None:
    print(f"[face] {msg}", flush=True)


def _peak_normalize(audio: np.ndarray, target: float = 0.75) -> np.ndarray:
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak < 1e-6:
        return audio
    return np.clip(audio * (target / peak), -1.0, 1.0).astype(np.float32)


def _transcribe_wake(stt: WhisperSTT, samples: np.ndarray, sample_rate: int, *, tag: str):
    audio = samples.astype(np.float32).reshape(-1)
    level = rms(audio)
    boosted = _peak_normalize(audio)
    text = stt.transcribe(
        boosted,
        sample_rate,
        initial_prompt=_WAKE_PROMPT,
        vad_filter=False,
        beam_size=3,
        min_rms=0.0004,
    )
    if not text and level >= _SPEECH_RMS * 0.5:
        hotter = np.clip(boosted * 1.8, -1.0, 1.0)
        text = stt.transcribe(
            hotter,
            sample_rate,
            initial_prompt=_WAKE_PROMPT,
            vad_filter=False,
            beam_size=3,
            min_rms=0.0003,
        )
        _log(f"{tag} STT retry hotter → {text!r}")

    match = score_wake(text)
    _log(
        f"{tag} STT_raw={text!r}  STT_norm={normalize_pt(text)!r}  rms={level:.4f}  "
        f"wake_hit={match.hit}  conf={match.score:.2f}  "
        f"best={match.best!r}  reason={match.reason}"
    )
    return text, match


def _transcribe_utterance(
    stt: WhisperSTT, samples: np.ndarray, sample_rate: int, *, tag: str
) -> str:
    audio = samples.astype(np.float32).reshape(-1)
    level = rms(audio)
    text = stt.transcribe(
        _peak_normalize(audio),
        sample_rate,
        vad_filter=False,
        beam_size=2,
        min_rms=0.0004,
        initial_prompt="Conversa em português com a Sally.",
    )
    if not text and level >= _SPEECH_RMS * 0.5:
        text = stt.transcribe(
            np.clip(_peak_normalize(audio) * 1.6, -1.0, 1.0),
            sample_rate,
            vad_filter=False,
            beam_size=2,
            min_rms=0.0003,
        )
    _log(
        f"{tag} STT_raw={text!r}  STT_norm={normalize_pt(text)!r}  "
        f"rms={level:.4f}"
    )
    return text


def _handle_user_text(
    *,
    ollama: OllamaClient,
    brain: ProactiveController,
    memory: LongTermMemory,
    face: FaceApp,
    label: str,
    brain_url: str = "",
) -> str:
    """Chat via VPS brain API if configured, else local memory+Ollama. Text only."""
    label = (label or "").strip()
    if not label:
        face.set_expression(FaceExpression.LISTENING, "sessão ativa — continua falando")
        return ""

    face.set_expression(FaceExpression.THINKING, "pensando…")

    # Prefer remote Sally brain (VPS): memory+ollama live there
    if brain_url.strip():
        _log(f"BRAIN ← {label!r}  url={brain_url.rstrip('/')}/v1/chat")
        remote = ask_brain(brain_url, label, timeout_s=90.0)
        if remote.ok and remote.reply:
            reply = remote.reply
            _log(f"brain reply={reply!r}  raw_memories={remote.raw.get('memories')}")
            face.set_expression(FaceExpression.HAPPY, reply[:90])
            brain.note_user_text(label, reply)
            time.sleep(2.0)
            face.set_expression(FaceExpression.LISTENING, "sessão ativa — continua falando")
            return reply
        _log(f"brain FAIL {remote.error} — falling back to local ollama")

    mem_block = memory.context_for_prompt(label, recent_n=6, relevant_n=6)
    epi = brain.episodic.recent_summary(limit=2)
    memory_context = f"{mem_block}\n---\n{epi}"
    _log(
        f"OLLAMA ← {label!r}  url={ollama.cfg.native_url}  model={ollama.cfg.model}  "
        f"memories={memory.count()}"
    )
    result = ollama.chat(label, memory_context=memory_context)
    if result.ok and result.text:
        reply = result.text
        _log(f"ollama reply={reply!r}  source={result.source}")
        face.set_expression(FaceExpression.HAPPY, reply[:90])
        brain.note_user_text(label, reply)
        memory.remember_exchange(label, reply)
        _log(f"memory saved — total={memory.count()}")
    else:
        reply = f"ollama erro: {(result.detail or 'sem resposta')[:70]}"
        _log(f"ollama FAIL {result.detail}")
        face.set_expression(FaceExpression.HAPPY, reply)
        brain.note_user_text(label, "")
        memory.remember_exchange(label, "")
    time.sleep(2.0)
    face.set_expression(FaceExpression.LISTENING, "sessão ativa — continua falando")
    return reply


def _run_conversation_session(
    *,
    ollama: OllamaClient,
    memory: LongTermMemory,
    stt: WhisperSTT,
    face: FaceApp,
    brain: ProactiveController,
    stop: threading.Event,
    sr: int,
    ch: int,
    first_utterance: str,
    session_silence_s: float,
    brain_url: str = "",
) -> None:
    """Active chat until silence timeout or goodbye. No wake word needed."""
    brain.set_busy(True)
    face.set_expression(FaceExpression.LISTENING, "sessão ativa — continua falando")
    _log(
        f"SESSION start — silence_end={session_silence_s:.0f}s  "
        f"first={first_utterance!r}"
    )

    if first_utterance.strip():
        if is_session_end(first_utterance):
            face.set_expression(FaceExpression.HAPPY, "tchau — sessão encerrada")
            brain.note_user_text(first_utterance, "tchau")
            _log("SESSION end — bye on first utterance")
            time.sleep(1.5)
            brain.set_busy(False)
            return
        _handle_user_text(
            ollama=ollama,
            brain=brain,
            memory=memory,
            face=face,
            label=first_utterance,
            brain_url=brain_url,
        )

    roll: deque[np.ndarray] = deque()
    roll_len = 0
    roll_max = int(_ROLL_S * sr)
    chunk_n = max(1, int(_CHUNK_S * sr))
    speech_hold = 0
    last_voice_ts = time.time()

    while not stop.is_set():
        if time.time() - last_voice_ts >= session_silence_s:
            face.set_expression(
                FaceExpression.IDLE,
                f"sessão encerrou ({int(session_silence_s)}s quieta)",
            )
            _log(f"SESSION end — silence ≥ {session_silence_s:.0f}s")
            time.sleep(1.2)
            break

        remaining = session_silence_s - (time.time() - last_voice_ts)
        face.set_expression(
            FaceExpression.LISTENING,
            f"sessão ativa · quieta em {max(0, int(remaining))}s",
        )

        rec = record_seconds(_CHUNK_S, sample_rate=sr, channels=ch)
        if stop.is_set():
            break
        chunk = rec.samples.astype(np.float32).reshape(-1)
        if chunk.size < chunk_n:
            chunk = np.pad(chunk, (0, chunk_n - chunk.size))
        elif chunk.size > chunk_n:
            chunk = chunk[:chunk_n]

        roll.append(chunk)
        roll_len += chunk.size
        while roll_len > roll_max and roll:
            dropped = roll.popleft()
            roll_len -= dropped.size

        level = rms(chunk)
        speaking = is_speech(chunk, threshold=_SPEECH_RMS) or level >= _SPEECH_RMS
        if speaking:
            speech_hold = _POST_SPEECH_CHUNKS
            last_voice_ts = time.time()
            continue

        if speech_hold <= 0:
            continue
        speech_hold -= 1
        if speech_hold > 0:
            continue

        buf = np.concatenate(list(roll)) if roll else chunk
        text = _transcribe_utterance(stt, buf, sr, tag="session")
        roll.clear()
        roll_len = 0

        # Optional leading Slice inside an open session — strip it
        if score_wake(text).hit:
            text = strip_wake_prefix(text)
        label = (text or "").strip()
        if not label:
            continue

        last_voice_ts = time.time()
        if is_session_end(label):
            face.set_expression(FaceExpression.HAPPY, "tchau — sessão encerrada")
            brain.note_user_text(label, "tchau")
            _log(f"SESSION end — bye phrase {label!r}")
            time.sleep(1.5)
            break

        _handle_user_text(
            ollama=ollama,
            brain=brain,
            memory=memory,
            face=face,
            label=label,
            brain_url=brain_url,
        )

    brain.set_busy(False)
    _log("SESSION closed — back to wake")


def run_face_listen_loop(
    *,
    max_cycles: int | None = None,
) -> None:
    settings = load_settings()
    face = FaceApp()
    ollama = OllamaClient(settings.ollama)
    mem_path = settings.project_root / "data" / "memory" / "sally_memory.db"
    if os.getenv("SALLY_MEMORY_DB", "").strip():
        mem_path = Path(os.getenv("SALLY_MEMORY_DB", "").strip())
    memory = LongTermMemory(mem_path)
    model = settings.voice.stt_model
    stt = WhisperSTT(
        model_size=model,
        device=settings.voice.stt_device,
        language=settings.voice.stt_language,
        min_rms=0.0004,
    )
    brain = ProactiveController(
        root=settings.project_root,
        stage=settings.lif.stage,
        enabled=settings.lif.enabled,
    )
    stop = threading.Event()
    sr = settings.voice.sample_rate
    ch = settings.voice.channels
    roll_max = int(_ROLL_S * sr)
    chunk_n = max(1, int(_CHUNK_S * sr))
    session_silence_s = float(
        os.getenv("SALLY_SESSION_SILENCE_S", str(_SESSION_SILENCE_S))
    )
    brain_url = os.getenv("SALLY_BRAIN_URL", "").strip()

    def on_close() -> None:
        stop.set()
        face.root.destroy()

    face.root.protocol("WM_DELETE_WINDOW", on_close)

    def proactive_worker() -> None:
        _log(
            f"proactive on — silence≥{brain.silence_threshold_s:.0f}s "
            f"cooldown={brain.cooldown_s:.0f}s hz≥{brain.speak_hz_threshold:.0f} "
            f"name={brain.episodic.user_name or '(desconhecido)'}  "
            f"TTS={'on' if settings.voice.tts_enabled else 'OFF (text only)'}"
        )
        while not stop.is_set():
            try:
                prop = brain.tick(steps=50)
                if prop is not None:
                    _log(
                        f"PROACTIVE fire conf_hz={prop.motor_hz:.1f} "
                        f"reason={prop.reason} text={prop.text!r}"
                    )
                    face.set_expression(FaceExpression.HAPPY, prop.text[:90])
                    _log(f"proactive TEXT (muted): {prop.text}")
                    time.sleep(3.0)
            except Exception as e:  # noqa: BLE001
                _log(f"proactive error: {e}")
            stop.wait(2.0)

    def worker() -> None:
        _log(f"carregando Whisper ({model})…")
        face.set_expression(FaceExpression.IDLE, "carregando ouvido…")
        _ = stt.transcribe(np.zeros(1600, dtype=np.float32), 16000, vad_filter=False)
        who = brain.episodic.user_name or "você"
        face.set_expression(FaceExpression.IDLE, f"aguardando Slice · LIF: {who}")
        ping = ollama.ping()
        _log(
            f"pronta — stt={model} wake=Slice  "
            f"brain_url={brain_url or '(local)'}  "
            f"ollama={settings.ollama.base_url} model={settings.ollama.model} "
            f"ping={'ok' if ping.ok else 'FAIL:'+ping.detail}  "
            f"sqlite={mem_path} memories={memory.count()}  "
            f"session_silence={session_silence_s:.0f}s  "
            f"TTS={'ON' if settings.voice.tts_enabled else 'OFF'}  "
            f"episodic={brain.episodic.recent_summary()}"
        )

        roll: deque[np.ndarray] = deque()
        roll_len = 0
        speech_hold = 0
        cycles = 0

        while not stop.is_set():
            if max_cycles is not None and cycles >= max_cycles:
                break

            if face.expression == FaceExpression.IDLE:
                face.set_expression(
                    FaceExpression.IDLE,
                    f"aguardando Slice · LIF: {brain.episodic.user_name or 'aprendendo'}",
                )
            rec = record_seconds(_CHUNK_S, sample_rate=sr, channels=ch)
            if stop.is_set():
                break

            chunk = rec.samples.astype(np.float32).reshape(-1)
            if chunk.size < chunk_n:
                chunk = np.pad(chunk, (0, chunk_n - chunk.size))
            elif chunk.size > chunk_n:
                chunk = chunk[:chunk_n]

            roll.append(chunk)
            roll_len += chunk.size
            while roll_len > roll_max and roll:
                dropped = roll.popleft()
                roll_len -= dropped.size

            level = rms(chunk)
            speaking = is_speech(chunk, threshold=_SPEECH_RMS) or level >= _SPEECH_RMS

            if speaking:
                speech_hold = _POST_SPEECH_CHUNKS
                _log(f"stage1 speech rms={level:.4f} — holding {_POST_SPEECH_CHUNKS} chunks")
                continue

            if speech_hold <= 0:
                continue
            speech_hold -= 1
            if speech_hold > 0:
                continue

            buf = np.concatenate(list(roll)) if roll else chunk
            text, match = _transcribe_wake(stt, buf, sr, tag="wake")
            roll.clear()
            roll_len = 0
            if not match.hit:
                time.sleep(_WAKE_COOLDOWN_S)
                continue

            first = strip_wake_prefix(text)
            _log(f"WAKE ok (Slice conf={match.score:.2f}) — entering session; resto={first!r}")
            _run_conversation_session(
                ollama=ollama,
                memory=memory,
                stt=stt,
                face=face,
                brain=brain,
                stop=stop,
                sr=sr,
                ch=ch,
                first_utterance=first,
                session_silence_s=session_silence_s,
                brain_url=brain_url,
            )
            cycles += 1

        _log("loop encerrado")
        face.close()

    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=proactive_worker, daemon=True).start()
    face.run()


def main() -> int:
    run_face_listen_loop()
    return 0
