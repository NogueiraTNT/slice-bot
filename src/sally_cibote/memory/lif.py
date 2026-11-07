"""Memória LIF leve (inspiração Pestinha — código próprio MIT, sem fork GPL).

Portátil: JSONL em disco. Estágios newborn → toddler → helper.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


STAGES = ("newborn", "toddler", "helper")


@dataclass
class LifMemory:
    path: Path
    stage: str = "newborn"
    confirmations: int = 0
    _recent: list[dict[str, Any]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self._load_tail()

    def _load_tail(self) -> None:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()[-200:]
            for line in lines:
                if not line.strip():
                    continue
                ev = json.loads(line)
                self._recent.append(ev)
                if ev.get("type") == "meta":
                    self.stage = ev.get("stage", self.stage)
                    self.confirmations = int(ev.get("confirmations", self.confirmations))
        except Exception:  # noqa: BLE001
            pass

    def _append(self, event: dict[str, Any]) -> None:
        event = {**event, "ts": time.time()}
        self._recent.append(event)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def remember_turn(self, user: str, assistant: str) -> None:
        self._append({"type": "turn", "user": user, "assistant": assistant, "stage": self.stage})

    def confirm(self) -> str:
        self.confirmations += 1
        if self.confirmations >= 8 and self.stage == "toddler":
            self.stage = "helper"
        elif self.confirmations >= 3 and self.stage == "newborn":
            self.stage = "toddler"
        self._append(
            {
                "type": "meta",
                "action": "CONFIRM",
                "stage": self.stage,
                "confirmations": self.confirmations,
            }
        )
        return self.stage

    def reject(self) -> str:
        self.confirmations = max(0, self.confirmations - 1)
        self._append(
            {
                "type": "meta",
                "action": "REJECT",
                "stage": self.stage,
                "confirmations": self.confirmations,
            }
        )
        return self.stage

    def context_snippet(self, limit: int = 4) -> str:
        turns = [e for e in self._recent if e.get("type") == "turn"][-limit:]
        if not turns:
            return f"Estagio LIF: {self.stage}."
        lines = [f"Estagio LIF: {self.stage} (confirmacoes={self.confirmations})."]
        for t in turns:
            lines.append(f"Usuario: {t.get('user', '')}")
            lines.append(f"Sally: {t.get('assistant', '')}")
        return "\n".join(lines)
