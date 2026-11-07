"""Episodic memory — who Daniel is + recent context (JSON, MIT original)."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_NAME_PATTERNS = (
    re.compile(
        r"(?:meu nome(?:\s+[eé])?|eu sou|me chamo|pode me chamar de)\s+([A-Za-zÀ-ÿ]{2,20})",
        re.IGNORECASE,
    ),
    re.compile(r"(?:i am|my name is)\s+([A-Za-z]{2,20})", re.IGNORECASE),
)


@dataclass
class EpisodicMemory:
    """Lightweight long-term facts + short recent event ring."""

    path: Path
    user_name: str = ""
    facts: dict[str, str] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    last_interaction_ts: float = 0.0
    proactive_count: int = 0
    max_events: int = 40

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return
        self.user_name = str(data.get("user_name") or "")
        self.facts = dict(data.get("facts") or {})
        self.events = list(data.get("events") or [])[-self.max_events :]
        self.last_interaction_ts = float(data.get("last_interaction_ts") or 0.0)
        self.proactive_count = int(data.get("proactive_count") or 0)

    def save(self) -> None:
        payload = {
            "user_name": self.user_name,
            "facts": self.facts,
            "events": self.events[-self.max_events :],
            "last_interaction_ts": self.last_interaction_ts,
            "proactive_count": self.proactive_count,
            "saved_at": time.time(),
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def silence_s(self, *, now: float | None = None) -> float:
        now = time.time() if now is None else now
        if self.last_interaction_ts <= 0:
            # Fresh boot: treat as already quiet so first proactive can fire after threshold
            return now - (now - 10_000)  # large silence
        return max(0.0, now - self.last_interaction_ts)

    def note_interaction(self, user: str, assistant: str = "", *, kind: str = "turn") -> None:
        self.last_interaction_ts = time.time()
        self.events.append(
            {
                "ts": self.last_interaction_ts,
                "kind": kind,
                "user": user,
                "assistant": assistant,
            }
        )
        self.events = self.events[-self.max_events :]
        learned = self.maybe_learn_name(user)
        if learned:
            self.facts["name_source"] = "utterance"
        self.save()

    def note_proactive(self, text: str) -> None:
        self.proactive_count += 1
        self.last_interaction_ts = time.time()
        self.events.append(
            {
                "ts": self.last_interaction_ts,
                "kind": "proactive",
                "user": "",
                "assistant": text,
            }
        )
        self.events = self.events[-self.max_events :]
        self.save()

    def maybe_learn_name(self, text: str) -> str | None:
        raw = (text or "").strip()
        if not raw:
            return None
        for pat in _NAME_PATTERNS:
            m = pat.search(raw)
            if not m:
                continue
            name = m.group(1).strip(" .,!?").title()
            if name.lower() in {"slice", "sally", "cibote", "voce", "você"}:
                continue
            self.user_name = name
            self.facts["preferred_name"] = name
            self.save()
            return name
        return None

    def set_name(self, name: str) -> None:
        self.user_name = name.strip().title()
        if self.user_name:
            self.facts["preferred_name"] = self.user_name
        self.save()

    def recent_summary(self, limit: int = 3) -> str:
        bits: list[str] = []
        if self.user_name:
            bits.append(f"Nome: {self.user_name}")
        for ev in self.events[-limit:]:
            if ev.get("kind") == "proactive":
                bits.append(f"Sally disse: {ev.get('assistant', '')[:60]}")
            elif ev.get("user"):
                bits.append(f"Daniel: {ev.get('user', '')[:60]}")
        return " | ".join(bits) if bits else "(sem episodios ainda)"
