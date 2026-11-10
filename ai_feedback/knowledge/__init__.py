"""Articulation knowledge base loader."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "articulation.json"


@lru_cache(maxsize=1)
def knowledge() -> dict:
    return json.loads(_PATH.read_text(encoding="utf-8"))


def normalise_ipa(sym: str | None) -> str | None:
    if sym is None:
        return None
    return {"g": "ɡ", "r": "r", "ɹ": "r", "ɚ": "ər", "ɝ": "ɜr"}.get(sym, sym)


def phoneme_note(sym: str | None) -> dict | None:
    sym = normalise_ipa(sym)
    return knowledge()["phonemes"].get(sym) if sym else None


def contrast_note(expected: str | None, realised: str | None) -> str | None:
    if not expected or not realised:
        return None
    return knowledge()["contrasts"].get(f"{normalise_ipa(expected)}>{normalise_ipa(realised)}")


def pattern_note(key: str) -> str | None:
    return knowledge()["patterns"].get(key)
