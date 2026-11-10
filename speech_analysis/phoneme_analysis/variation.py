"""Accepted pronunciation variation (accent and allophone tolerance).

Two mechanisms keep valid accents from being penalised:

1. **Whole-word variants** in the word database (General American, CMUdict
   alternates, British RP).  Every variant is scored and the best-explained
   one is used.
2. **Context rules** below, applied per phone.  If an accepted realisation
   explains the audio better than the canonical phone, the phone counts as
   correct and the result notes which variant was accepted.

Rules are deliberately conservative: a rule that is too broad would hide
genuine speech-sound errors (e.g. accepting /w/ for /r/ would defeat /r/
practice).  Edit with care and add a test for every new rule.
"""

from __future__ import annotations

from .phonemes import is_vowel, split_stress

# Candidate labels used across engines.  "AH" = stressed /ʌ/, "AH0" = schwa.
CANDIDATE_LABELS = [
    "AA", "AE", "AH", "AH0", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW",
    "B", "CH", "D", "DH", "F", "G", "HH", "JH", "K", "L", "M", "N", "NG", "P", "R", "S", "SH", "T",
    "TH", "V", "W", "Y", "Z", "ZH",
]


def label_for(phone: str) -> str:
    """Map an ARPAbet phone with stress to a candidate label."""
    base, stress = split_stress(phone)
    if base == "AH" and stress == 0:
        return "AH0"
    return base


def accepted_alternatives(arpabet: list[str], i: int) -> list[str]:
    """Candidate labels accepted as correct realisations of ``arpabet[i]`` in context."""
    phone = arpabet[i]
    base, stress = split_stress(phone)
    prev_p = arpabet[i - 1] if i > 0 else None
    next_p = arpabet[i + 1] if i + 1 < len(arpabet) else None
    out: list[str] = []
    # cot-caught merger (most of North America, Scotland)
    if base == "AA":
        out.append("AO")
    if base == "AO":
        out.append("AA")
    # unstressed vowel reduction: schwa ~ /ɪ/ (rabbit, roses, wanted)
    if stress == 0 and base in {"AH", "IH"}:
        out.extend(["AH0", "IH"])
    if stress == 0 and base == "IY":  # happy-tensing variation
        out.append("IH")
    # flapping: /t/, /d/ between vowels before an unstressed vowel (butter, water)
    if base in {"T", "D"} and prev_p and next_p and is_vowel(prev_p) and is_vowel(next_p) \
            and split_stress(next_p)[1] == 0:
        out.append("D" if base == "T" else "T")
    lab = label_for(phone)
    return [x for x in dict.fromkeys(out) if x != lab]
