"""Long-term memory for Sally — local SQLite only."""

from __future__ import annotations

import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path


_STOP = {
    "a",
    "o",
    "as",
    "os",
    "de",
    "da",
    "do",
    "e",
    "é",
    "um",
    "uma",
    "pra",
    "para",
    "com",
    "que",
    "no",
    "na",
    "em",
    "eu",
    "me",
    "meu",
    "minha",
    "voce",
    "você",
    "se",
    "por",
    "mais",
    "menos",
    "como",
    "foi",
    "ser",
    "tem",
    "tá",
    "ta",
    "ai",
    "aí",
    "ola",
    "olá",
    "slice",
    "sally",
    "temos",
    "tenho",
    "sobre",
}

# Tokens that should pull agenda/reminder rows even if they aged out of recent()
_SCHEDULE = {
    "amanha",
    "manha",
    "reuniao",
    "compromisso",
    "agenda",
    "lembrete",
    "marcar",
    "marcado",
    "horario",
    "depois",
}


@dataclass(frozen=True)
class MemoryRow:
    id: int
    timestamp: float
    content: str
    tag: str


class LongTermMemory:
    """SQLite memories: id, timestamp, content, tag."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    content TEXT NOT NULL,
                    tag TEXT NOT NULL DEFAULT 'general'
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_ts ON memories(timestamp DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_tag ON memories(tag)"
            )
            conn.commit()

    def add(self, content: str, *, tag: str = "general", ts: float | None = None) -> int:
        text = (content or "").strip()
        if not text:
            return -1
        tag = (tag or "general").strip().lower()[:40] or "general"
        when = time.time() if ts is None else float(ts)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO memories (timestamp, content, tag) VALUES (?, ?, ?)",
                (when, text[:2000], tag),
            )
            conn.commit()
            return int(cur.lastrowid or -1)

    def remember_exchange(self, user: str, assistant: str) -> None:
        """Persist one turn (user + sally) with light auto-tags."""
        user = (user or "").strip()
        assistant = (assistant or "").strip()
        if user:
            self.add(f"Daniel: {user}", tag=self._tag_for(user, role="user"))
        if assistant:
            self.add(f"Sally: {assistant}", tag="sally")
        # Promote clear reminders / facts
        fact = self._extract_fact(user)
        if fact:
            self.add(fact, tag="fact")

    def recent(self, limit: int = 12) -> list[MemoryRow]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, timestamp, content, tag FROM memories "
                "ORDER BY timestamp DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [self._row(r) for r in rows]

    def by_tags(self, tags: tuple[str, ...], *, limit: int = 40) -> list[MemoryRow]:
        """All rows with given tags (newest first), not limited to recent window."""
        clean = tuple(t.strip().lower() for t in tags if t.strip())
        if not clean:
            return []
        placeholders = ",".join("?" for _ in clean)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT id, timestamp, content, tag FROM memories "
                f"WHERE tag IN ({placeholders}) "
                f"ORDER BY timestamp DESC LIMIT ?",
                (*clean, max(1, limit)),
            ).fetchall()
        return [self._row(r) for r in rows]

    def search(self, query: str, *, limit: int = 8) -> list[MemoryRow]:
        """Keyword relevance with accent folding; always includes fact/reminder pool."""
        tokens = self._tokens(query)
        if not tokens:
            return self.recent(limit=limit)

        pool: dict[int, MemoryRow] = {r.id: r for r in self.recent(limit=max(200, limit * 20))}
        # Facts/reminders must not age out of retrieval
        for r in self.by_tags(("fact", "reminder"), limit=60):
            pool[r.id] = r

        schedule_hit = bool(_SCHEDULE.intersection(tokens))
        if schedule_hit:
            # Full-table scan for schedule keywords (DB is small; keeps old meetings)
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT id, timestamp, content, tag FROM memories "
                    "ORDER BY timestamp DESC LIMIT 500"
                ).fetchall()
            for r in rows:
                row = self._row(r)
                hay = self._fold(row.content)
                if any(t in hay for t in tokens if t in _SCHEDULE or len(t) >= 4):
                    pool[row.id] = row

        scored: list[tuple[int, MemoryRow]] = []
        for row in pool.values():
            hay = self._fold(row.content)
            hits = sum(1 for t in tokens if t in hay)
            if not hits:
                continue
            bonus = 0
            if row.tag == "fact":
                bonus += 6
            elif row.tag == "reminder":
                bonus += 4
            # Real commitments beat question echoes / failed answers
            if any(k in hay for k in ("combinado:", "anotado:", "marcar ", "reuniao", "compromisso")):
                bonus += 4
            if "nada marcado" in hay or "vamos verificar" in hay:
                bonus -= 5
            if "?" in row.content or any(
                k in hay for k in ("o que temos", "o que tenho", "resume o que", "qual e a", "que horas")
            ):
                bonus -= 6
            scored.append((hits * 2 + bonus, row))
        scored.sort(key=lambda x: (-x[0], -x[1].timestamp))
        if not scored:
            return self.recent(limit=limit)
        return [r for _, r in scored[:limit]]

    def context_for_prompt(self, query: str, *, recent_n: int = 6, relevant_n: int = 6) -> str:
        """Blend relevant (first) + recent memories into a short prompt block."""
        recent = self.recent(limit=recent_n)
        relevant = self.search(query, limit=relevant_n)
        # Prefer concrete facts/reminders; demote interrogative echoes
        def _rank(r: MemoryRow) -> tuple[int, int, float]:
            hay = self._fold(r.content)
            interrog = 1 if ("?" in r.content or "o que temos" in hay or "o que tenho" in hay) else 0
            tag_rank = 0 if r.tag == "fact" else (1 if r.tag == "reminder" else 2)
            return (interrog, tag_rank, -r.timestamp)

        relevant = sorted(relevant, key=_rank)
        seen: set[int] = set()
        lines: list[str] = []
        for row in relevant + recent:
            if row.id in seen:
                continue
            seen.add(row.id)
            lines.append(f"[{row.tag}] {row.content}")
            if len(lines) >= recent_n + relevant_n:
                break
        if not lines:
            return "(sem memorias ainda)"
        return "\n".join(lines)

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM memories").fetchone()
        return int(row["n"] if row else 0)

    @staticmethod
    def _row(r: sqlite3.Row) -> MemoryRow:
        return MemoryRow(
            id=int(r["id"]),
            timestamp=float(r["timestamp"]),
            content=str(r["content"]),
            tag=str(r["tag"]),
        )

    @staticmethod
    def _fold(text: str) -> str:
        """Lowercase + strip accents so amanhã matches amanha."""
        norm = unicodedata.normalize("NFKD", text or "")
        return "".join(c for c in norm if not unicodedata.combining(c)).lower()

    @classmethod
    def _tokens(cls, text: str) -> list[str]:
        folded = cls._fold(text)
        raw = re.findall(r"[a-z0-9]{3,}", folded)
        return [t for t in raw if t not in _STOP][:24]

    @classmethod
    def _tag_for(cls, text: str, *, role: str) -> str:
        low = cls._fold(text)
        # Only imperative schedule language — not questions like "o que temos amanha?"
        if any(k in low for k in ("lembra", "lembrete", "marcar", "marca ", "anota", "agendar")):
            return "reminder"
        if any(k in low for k in ("meu nome", "eu sou", "me chamo")):
            return "fact"
        return "user" if role == "user" else "general"

    @staticmethod
    def _extract_fact(text: str) -> str | None:
        low = (text or "").strip()
        if not low:
            return None
        # "marcar amanhã para X" / "lembra que Y"
        m = re.search(
            r"(?:marcar|marca|lembra(?:r)?(?:\s+que)?|anota(?:r)?)\s+(.+)$",
            low,
            flags=re.IGNORECASE,
        )
        if m:
            return f"Combinado: {m.group(1).strip()}"
        m2 = re.search(
            r"(?:meu nome(?:\s+[eé])?|eu sou|me chamo)\s+([A-Za-zÀ-ÿ]{2,20})",
            low,
            flags=re.IGNORECASE,
        )
        if m2:
            return f"Nome do usuario: {m2.group(1).strip().title()}"
        return None
