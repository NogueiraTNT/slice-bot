"""Detect end-of-conversation phrases (no wake required)."""

from __future__ import annotations

from sally_cibote.voice.wake import normalize_pt

_BYE_PHRASES = (
    "tchau",
    "chau",
    "ate logo",
    "ate mais",
    "flw",
    "falou",
    "encerra",
    "encerrar",
    "desligar",
    "pode parar",
    "para ai",
    "para aí",
    "obrigado slice",
    "obrigada slice",
    "slice tchau",
    "tchau slice",
)


def is_session_end(text: str) -> bool:
    norm = normalize_pt(text)
    if not norm:
        return False
    compact = norm.replace(" ", "")
    for phrase in _BYE_PHRASES:
        p = normalize_pt(phrase).replace(" ", "")
        if p and p in compact:
            return True
    # lone short goodbyes
    toks = norm.split()
    if toks and toks[-1] in ("tchau", "chau", "flw"):
        return True
    return False
