"""Pronunciation lookup helpers (build-time and optional runtime G2P).

* :func:`cmudict_pronunciations` - US English pronunciations with stress from
  the CMU Pronouncing Dictionary (``pip install cmudict``).
* :func:`espeak_ipa` - IPA from the ``espeak-ng`` phonemizer for any voice,
  e.g. ``en-gb`` for British Received Pronunciation.
* :func:`espeak_ipa_to_arpabet` - converts espeak's IPA to ARPAbet so British
  variants can be scored with the same phone inventory.

None of these are needed at analysis time: the word database stores the final
ARPAbet sequences.  They are used by ``scripts/build_word_database.py`` and by
the custom-word admin endpoint when available.
"""

from __future__ import annotations

import shutil
import subprocess
import unicodedata
from functools import lru_cache

from .phonemes import is_vowel, split_stress

# Longest-match-first token table: espeak IPA -> ARPAbet (without stress).
_ESPEAK_TOKENS: list[tuple[str, list[str]]] = sorted(
    [
        ("aɪə", ["AY", "AH"]),
        ("aʊə", ["AW", "AH"]),
        ("tʃ", ["CH"]),
        ("dʒ", ["JH"]),
        ("eɪ", ["EY"]),
        ("aɪ", ["AY"]),
        ("ɔɪ", ["OY"]),
        ("əʊ", ["OW"]),
        ("oʊ", ["OW"]),
        ("aʊ", ["AW"]),
        ("ɪə", ["IH", "AH"]),
        ("eə", ["EH", "AH"]),
        ("ɛə", ["EH", "AH"]),
        ("ʊə", ["UH", "AH"]),
        ("iː", ["IY"]),
        ("uː", ["UW"]),
        ("ɑː", ["AA"]),
        ("ɔː", ["AO"]),
        ("ɜː", ["ER"]),
        ("ɑ", ["AA"]),
        ("ɔ", ["AO"]),
        ("ɜ", ["ER"]),
        ("ɚ", ["ER"]),
        ("ɝ", ["ER"]),
        ("i", ["IY"]),
        ("ɪ", ["IH"]),
        ("ᵻ", ["IH"]),
        ("e", ["EH"]),
        ("ɛ", ["EH"]),
        ("æ", ["AE"]),
        ("a", ["AE"]),
        ("ɒ", ["AA"]),
        ("ʌ", ["AH"]),
        ("ə", ["AH"]),
        ("ɐ", ["AH"]),
        ("ʊ", ["UH"]),
        ("u", ["UW"]),
        ("o", ["OW"]),
        ("n̩", ["AH", "N"]),
        ("l̩", ["AH", "L"]),
        ("m̩", ["AH", "M"]),
        ("p", ["P"]),
        ("b", ["B"]),
        ("t", ["T"]),
        ("d", ["D"]),
        ("k", ["K"]),
        ("ɡ", ["G"]),
        ("g", ["G"]),
        ("f", ["F"]),
        ("v", ["V"]),
        ("θ", ["TH"]),
        ("ð", ["DH"]),
        ("s", ["S"]),
        ("z", ["Z"]),
        ("ʃ", ["SH"]),
        ("ʒ", ["ZH"]),
        ("h", ["HH"]),
        ("m", ["M"]),
        ("n", ["N"]),
        ("ŋ", ["NG"]),
        ("l", ["L"]),
        ("ɫ", ["L"]),
        ("ɹ", ["R"]),
        ("r", ["R"]),
        ("w", ["W"]),
        ("j", ["Y"]),
        ("ʔ", ["T"]),
        ("ɾ", ["T"]),
        ("x", ["K"]),
    ],
    key=lambda kv: -len(kv[0]),
)
_IGNORED = set(".-‿ʲ̃ːˑ ")


def espeak_ipa_to_arpabet(ipa: str) -> list[str]:
    """Convert espeak-ng IPA (``"təmˈɑːtəʊ"``) to ARPAbet with stress digits."""
    s = unicodedata.normalize("NFC", ipa.strip().strip("/"))
    out: list[str] = []
    pending_stress = 0
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "ˈ":
            pending_stress = 1
            i += 1
            continue
        if ch == "ˌ":
            pending_stress = 2
            i += 1
            continue
        if ch in _IGNORED:
            i += 1
            continue
        for tok, arpa in _ESPEAK_TOKENS:
            if s.startswith(tok, i):
                first_vowel_done = False
                for p in arpa:
                    if is_vowel(p):
                        stress = pending_stress if not first_vowel_done else 0
                        out.append(f"{p}{stress}")
                        first_vowel_done = True
                    else:
                        out.append(p)
                if first_vowel_done:
                    pending_stress = 0
                i += len(tok)
                break
        else:
            raise ValueError(f"Unsupported espeak IPA symbol {ch!r} in {ipa!r}")
    return out


def espeak_available() -> bool:
    return shutil.which("espeak-ng") is not None


def espeak_ipa(text: str, voice: str = "en-us") -> str:
    """Phonemize ``text`` with espeak-ng (raises if espeak-ng is not installed)."""
    exe = shutil.which("espeak-ng")
    if exe is None:
        raise RuntimeError("espeak-ng is not installed")
    res = subprocess.run(
        [exe, "-q", "--ipa", "-v", voice, text], capture_output=True, text=True, check=True, timeout=10
    )
    return res.stdout.strip()


@lru_cache(maxsize=1)
def _cmudict():
    import cmudict  # optional dependency

    return cmudict.dict()


def cmudict_pronunciations(word: str) -> list[list[str]]:
    try:
        return [list(p) for p in _cmudict().get(word.lower(), [])]
    except ImportError:
        return []


def strip_stress(arpabet: list[str]) -> tuple[str, ...]:
    return tuple(split_stress(p)[0] for p in arpabet)
