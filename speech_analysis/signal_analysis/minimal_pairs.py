"""Minimal-pair standards: generated recordings of common mistakes, e.g. "wabbit" for "rabbit".

Two different voices saying "rabbit" differ more, as waveforms, than one voice
saying "rabbit" and "wabbit". So instead of only asking "how close is the
recording to the standard?", the recording is also compared with a standard of
each common mistake spoken by the *same* generated voice. The difference

    contrast = distance(recording, correct standard) - distance(recording, mistake standard)

cancels most of the voice difference (both standards share the voice); averaged
over the standard voices, a clearly positive contrast means the recording is
closer to the mistake. The contrast is turned into a probability with a
calibrated logistic curve (``scripts/calibrate_signal.py``).

The mistakes checked are common consonant substitutions and deletions, and a
common confusion of the stressed vowel. A mistake outside this list is still
caught (less reliably) by the overall similarity to the standard.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..phoneme_analysis.phonemes import is_vowel

# Common substitutions in speech development and second-language learning (ARPAbet):
# gliding (r, l -> w), lisping (s, z -> th), fronting (k, g -> t, d; sh -> s),
# stopping (f, v, th, dh, j -> p, b, f, d, d), and ng -> n.
SUBSTITUTIONS = {
    "R": "W", "L": "W", "S": "TH", "Z": "DH", "SH": "S", "CH": "SH", "K": "T", "G": "D",
    "F": "P", "V": "B", "TH": "F", "DH": "D", "JH": "D", "NG": "N",
}
# Common confusions of the stressed vowel (e.g. "bet" for "bat", "sheep" for "ship").
VOWEL_SUBSTITUTIONS = {
    "AE": "EH", "EH": "AE", "IH": "IY", "IY": "IH", "UH": "UW", "UW": "UH", "AH": "AA", "AA": "AH",
    "AO": "OW", "OW": "AO", "EY": "EH", "AY": "AA", "ER": "AH", "AW": "AA", "OY": "OW",
}
MAX_PER_WORD = 5


def _base(p: str) -> str:
    return p.rstrip("012")


@dataclass(frozen=True)
class Mistake:
    key: str  # stable id, e.g. "sub0-R-W", "cluster", "final"
    kind: str  # "substitution" | "deletion"
    index: int  # position of the affected sound in the correct pronunciation
    expected: str  # ARPAbet of the expected sound
    realized: str | None  # ARPAbet of the sound said instead (None = left out)
    arpabet: tuple[str, ...]  # the mistaken pronunciation


def mistakes_for(arpabet: list[str]) -> list[Mistake]:
    """Common mistakes for a word, earliest sounds first (at most ``MAX_PER_WORD``)."""
    out: list[Mistake] = []
    for i, p in enumerate(arpabet):
        b = _base(p)
        if b in SUBSTITUTIONS:
            new = list(arpabet)
            new[i] = SUBSTITUTIONS[b]
            out.append(Mistake(f"sub{i}-{b}-{SUBSTITUTIONS[b]}", "substitution", i, b, SUBSTITUTIONS[b], tuple(new)))
    for i, p in enumerate(arpabet):  # the stressed vowel
        b = _base(p)
        if p.endswith("1") and b in VOWEL_SUBSTITUTIONS:
            new = list(arpabet)
            new[i] = VOWEL_SUBSTITUTIONS[b] + "1"
            out.append(Mistake(f"vowel{i}-{b}-{VOWEL_SUBSTITUTIONS[b]}", "substitution", i, b,
                               VOWEL_SUBSTITUTIONS[b], tuple(new)))
            break
    if len(arpabet) >= 3 and not is_vowel(arpabet[0]) and not is_vowel(arpabet[1]):
        out.append(Mistake("cluster", "deletion", 0, _base(arpabet[0]), None, tuple(arpabet[1:])))
    if len(arpabet) >= 3 and not is_vowel(arpabet[-1]):
        out.append(Mistake("final", "deletion", len(arpabet) - 1, _base(arpabet[-1]), None, tuple(arpabet[:-1])))
    seen, unique = {tuple(arpabet)}, []
    for m in sorted(out, key=lambda m: m.index):
        if m.arpabet not in seen:
            seen.add(m.arpabet)
            unique.append(m)
    return unique[:MAX_PER_WORD]
