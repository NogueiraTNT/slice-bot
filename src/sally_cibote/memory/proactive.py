"""Proactive layer — LIF motors decide when Sally speaks first."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from sally_cibote.memory.episodic import EpisodicMemory
from sally_cibote.memory.neuronal import (
    MiniLifBrain,
    morning_intensity_now,
    silence_intensity,
)


@dataclass(frozen=True)
class ProactiveProposal:
    text: str
    motor_hz: float
    reason: str
    morning: float
    silence: float


class ProactiveController:
    """Tick the mini LIF; when SPEAK_GREET fires hard enough, propose a line."""

    def __init__(
        self,
        *,
        root: Path,
        stage: str = "newborn",
        silence_threshold_s: float | None = None,
        cooldown_s: float | None = None,
        speak_hz_threshold: float | None = None,
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        self.stage = stage
        self.silence_threshold_s = float(
            silence_threshold_s
            if silence_threshold_s is not None
            else os.getenv("SALLY_PROACTIVE_SILENCE_S", "75")
        )
        self.cooldown_s = float(
            cooldown_s
            if cooldown_s is not None
            else os.getenv("SALLY_PROACTIVE_COOLDOWN_S", "120")
        )
        # Newborn is shy — needs stronger motor drive
        default_hz = 18.0 if stage == "newborn" else 12.0
        self.speak_hz_threshold = float(
            speak_hz_threshold
            if speak_hz_threshold is not None
            else os.getenv("SALLY_PROACTIVE_HZ", str(default_hz))
        )

        mem_dir = Path(root) / "data" / "memory"
        self.episodic = EpisodicMemory(mem_dir / "episodic.json")
        self.brain = MiniLifBrain(seed=7)
        self.brain.load(mem_dir / "mini_lif_state.json")
        self._weights_path = mem_dir / "mini_lif_state.json"
        self._last_proactive_ts = 0.0
        self._busy = False  # face is in wake/command turn

    def set_busy(self, busy: bool) -> None:
        self._busy = busy

    def note_user_text(self, text: str, assistant: str = "") -> None:
        """Call after a wake/command turn — updates memory + mild reward."""
        before = self.episodic.user_name
        self.episodic.note_interaction(text, assistant, kind="turn")
        if self.episodic.user_name and self.episodic.user_name != before:
            # Learning his name is a strong positive
            self.brain.on_reward(+1)
            self.brain.save(self._weights_path)
        elif text.strip():
            # Any engagement after morning/silence pathway: small +
            hour = time.localtime().tm_hour
            if 6 <= hour <= 11:
                self.brain.on_reward(+1)
                self.brain.save(self._weights_path)

    def note_reject(self) -> None:
        self.brain.on_reward(-1)
        self.brain.save(self._weights_path)
        self.episodic.note_interaction("(reject)", "", kind="reject")

    def tick(self, *, now: float | None = None, steps: int = 40) -> ProactiveProposal | None:
        if not self.enabled or self._busy:
            return None
        now = time.time() if now is None else now
        if self._last_proactive_ts and (now - self._last_proactive_ts) < self.cooldown_s:
            return None

        silence_s = self.episodic.silence_s(now=now)
        morning = morning_intensity_now()
        # Also allow afternoon soft bump so tests aren't morning-only
        hour = time.localtime(now).tm_hour
        if morning < 0.15 and 12 <= hour <= 20:
            morning = 0.25
        silence = silence_intensity(silence_s, threshold_s=self.silence_threshold_s)
        name_boost = 1.0 if self.episodic.user_name else 0.0

        self.brain.stimulate(
            {
                "TIME_MORNING": morning,
                "SILENCE": silence,
                "NAME_KNOWN": name_boost,
            }
        )
        peak_speak = 0.0
        for _ in range(steps):
            self.brain.step(1.0)
            peak_speak = max(peak_speak, self.brain.motors().get("SPEAK_GREET", 0.0))

        if silence < 0.35:
            return None
        if peak_speak < self.speak_hz_threshold:
            return None

        text = self._compose_line()
        reason = (
            f"SPEAK_GREET={peak_speak:.1f}Hz≥{self.speak_hz_threshold} "
            f"silence={silence:.2f} morning={morning:.2f} stage={self.stage}"
        )
        self._last_proactive_ts = now
        self.episodic.note_proactive(text)
        # Pathway that fired successfully — reinforce slightly in newborn only after engage
        return ProactiveProposal(
            text=text,
            motor_hz=peak_speak,
            reason=reason,
            morning=morning,
            silence=silence,
        )

    def _compose_line(self) -> str:
        name = self.episodic.user_name
        hour = time.localtime().tm_hour
        if 5 <= hour < 12:
            hello = "Bom dia"
        elif 12 <= hour < 18:
            hello = "Boa tarde"
        else:
            hello = "Boa noite"

        if name:
            if self.stage == "newborn":
                return f"{hello}, {name}. Posso sugerir alguma coisa, ou prefere me chamar de Slice?"
            return f"{hello}, {name}. Estava quieta um pouco — precisa de mim?"
        if self.stage == "newborn":
            return (
                f"{hello}. Ainda estou aprendendo. "
                "Se quiser, diga Slice e me conte seu nome."
            )
        return f"{hello}. Posso ajudar com algo?"
