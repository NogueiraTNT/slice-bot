"""Wake-word helpers for Sally (local STT text match).

Canonical wake: **Slice** (S-L-I-C-E — “fatia”). Daniel may say it alone.
STT often returns near-misses: e-lice, aslice, lice, slyce, etc.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


# Exact / near spellings STT often produces for "Slice".
WAKE_TOKENS = (
    "slice",
    "slyce",
    "slise",
    "slyse",
    "slicey",
    "slycey",
    "slices",
    "sliced",
    "aslice",
    "aslise",
    "eslice",
    "oslice",
    # Whisper often drops/splits the leading S → "lice" / "é lice" / "e-lice"
    "lice",
    "lyse",
    "lyce",
    "elice",
    "elise",
    "alice",  # occasional STT
    "ilis",
    "ilece",
    "sleice",
    "sleise",
    "flies",  # rare mishear
    "spice",  # occasional
)

# Phonetic / compact needles searched inside glued STT text.
WAKE_NEEDLES = (
    "slice",
    "slyce",
    "slise",
    "slyse",
    "aslice",
    "aslise",
    "eslice",
    "elice",
    "elise",
    "lice",
    "lyce",
    "lyse",
    "slic",
    "slys",
    "aslic",
    "sleic",
    "sleis",
)

# Optional crumbs STT puts around Slice ("é lice", "e lice")
WAKE_NOISE = ("e", "eh", "ei", "a", "ah", "o", "oh", "ee", "he")

# Optional greetings before the name (still accepted).
WAKE_PREFIXES = ("ola", "oi", "ei", "hey", "eae", "iae", "seu", "ei o", "fala", "alo")

# Canonical forms for scoring
_CANONICAL = ("slice", "lice", "elice", "aslice", "slyce", "slise")


def normalize_pt(text: str) -> str:
    text = (text or "").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    # keep letters/digits; turn punctuation/hyphens into spaces ("e-lice" → "e lice")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokens(norm: str) -> list[str]:
    return [t for t in norm.split() if t]


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def _is_wake_token(t: str) -> bool:
    if t in WAKE_TOKENS:
        return True
    if len(t) >= 4 and any(
        t.startswith(p)
        for p in ("slic", "slys", "slis", "aslic", "eslic", "lice", "lyce", "elic", "elis", "sleic")
    ):
        return True
    # Edit-distance soft match vs short canonical forms
    for c in _CANONICAL:
        if abs(len(t) - len(c)) <= 2 and _levenshtein(t, c) <= 1:
            return True
    return False


@dataclass(frozen=True)
class WakeMatch:
    """Result of scoring an STT hypothesis against Slice."""

    hit: bool
    score: float  # 0.0 .. 1.0
    best: str  # best matching token/needle or ""
    reason: str


def score_wake(text: str, *, threshold: float = 0.55) -> WakeMatch:
    """Fuzzy/phonetic score for how close `text` is to the Slice wake word."""
    norm = normalize_pt(text)
    if not norm:
        return WakeMatch(False, 0.0, "", "empty")

    toks = _tokens(norm)
    compact = norm.replace(" ", "")
    best_score = 0.0
    best = ""
    reason = "no-match"

    # 1) Exact token hits
    for t in toks:
        if t in WAKE_TOKENS:
            sc = 1.0 if t in ("slice", "slyce", "slise", "aslice", "elice") else 0.92
            if sc > best_score:
                best_score, best, reason = sc, t, "exact-token"

    # 2) Prefix / edit-distance token hits
    for t in toks:
        if _is_wake_token(t) and t not in WAKE_TOKENS:
            # distance to nearest canonical
            dist = min(_levenshtein(t, c) for c in _CANONICAL)
            sc = max(0.0, 0.9 - 0.15 * dist)
            if sc > best_score:
                best_score, best, reason = sc, t, f"fuzzy-token d={dist}"

    # 3) Compact substring needles (glued STT: olaslice, e-lice→elice)
    for needle in WAKE_NEEDLES:
        if needle in compact:
            # longer needles are more confident
            sc = min(1.0, 0.7 + 0.05 * len(needle))
            if needle in ("lice", "lyce", "lyse"):
                sc = 0.78  # short; still accept (common Whisper drop of S)
            if sc > best_score:
                best_score, best, reason = sc, needle, "substring"

    # 4) Sliding window edit distance on compact text vs "slice"/"lice"
    for target in ("slice", "slyce", "slise", "lice", "elice", "aslice"):
        n = len(target)
        if len(compact) < n - 1:
            continue
        for i in range(0, max(1, len(compact) - n + 2)):
            window = compact[i : i + n]
            if not window:
                continue
            dist = _levenshtein(window, target)
            if dist <= 1:
                sc = 0.95 if dist == 0 else 0.8
                if sc > best_score:
                    best_score, best, reason = sc, window, f"window≈{target} d={dist}"

    # 5) "e" / "a" + lice split across tokens
    for i, t in enumerate(toks[:-1]):
        if t in WAKE_NOISE and _is_wake_token(toks[i + 1]):
            sc = 0.9
            pair = f"{t} {toks[i + 1]}"
            if sc > best_score:
                best_score, best, reason = sc, pair, "noise+token"

    hit = best_score >= threshold
    return WakeMatch(hit, round(best_score, 3), best, reason)


def contains_wake_word(text: str) -> bool:
    """True if utterance contains Slice (alone or with a short greeting)."""
    return score_wake(text).hit


def strip_wake_prefix(text: str) -> str:
    """Remove wake token / greeting+wake; return remaining command text."""
    norm = normalize_pt(text)
    toks = _tokens(norm)
    if not toks:
        return ""

    out: list[str] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in WAKE_PREFIXES or t in WAKE_NOISE:
            # skip greeting/noise; if next is wake, skip that too
            i += 1
            if i < len(toks) and _is_wake_token(toks[i]):
                i += 1
            continue
        if _is_wake_token(t):
            i += 1
            continue
        out.append(t)
        i += 1
    return " ".join(out)
