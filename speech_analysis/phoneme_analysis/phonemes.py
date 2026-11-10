"""English phoneme inventory shared by every component.

The canonical representation throughout the system is **ARPAbet with stress
digits** (CMU Pronouncing Dictionary convention, e.g. ``B AH1 T ER0 F L AY2``).
It is unambiguous, ASCII-only, and matches the phone sets of common English
acoustic models and of the speechocean762 evaluation corpus.

For display we derive broad IPA (General American), e.g. ``/ˈbʌtərˌflaɪ/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VOWELS = {
    "AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW",
}
CONSONANTS = {
    "B", "CH", "D", "DH", "F", "G", "HH", "JH", "K", "L", "M", "N", "NG", "P", "R", "S",
    "SH", "T", "TH", "V", "W", "Y", "Z", "ZH",
}
ALL_PHONES = sorted(VOWELS | CONSONANTS)


@dataclass(frozen=True)
class PhonemeInfo:
    arpabet: str
    ipa: str
    kind: str  # "vowel" | "consonant"
    example: str
    features: dict = field(default_factory=dict)


def _c(arpa, ipa, place, manner, voiced, example):
    return PhonemeInfo(arpa, ipa, "consonant", example, {"place": place, "manner": manner, "voiced": voiced})


def _v(arpa, ipa, height, backness, rounded, example, diphthong=False, rhotic=False):
    return PhonemeInfo(
        arpa, ipa, "vowel", example,
        {"height": height, "backness": backness, "rounded": rounded, "diphthong": diphthong, "rhotic": rhotic},
    )


PHONEMES: dict[str, PhonemeInfo] = {
    # consonants
    "P": _c("P", "p", "bilabial", "stop", False, "pen"),
    "B": _c("B", "b", "bilabial", "stop", True, "bat"),
    "T": _c("T", "t", "alveolar", "stop", False, "top"),
    "D": _c("D", "d", "alveolar", "stop", True, "dog"),
    "K": _c("K", "k", "velar", "stop", False, "cat"),
    "G": _c("G", "ɡ", "velar", "stop", True, "go"),
    "F": _c("F", "f", "labiodental", "fricative", False, "fan"),
    "V": _c("V", "v", "labiodental", "fricative", True, "van"),
    "TH": _c("TH", "θ", "dental", "fricative", False, "thumb"),
    "DH": _c("DH", "ð", "dental", "fricative", True, "this"),
    "S": _c("S", "s", "alveolar", "fricative", False, "sun"),
    "Z": _c("Z", "z", "alveolar", "fricative", True, "zoo"),
    "SH": _c("SH", "ʃ", "postalveolar", "fricative", False, "shoe"),
    "ZH": _c("ZH", "ʒ", "postalveolar", "fricative", True, "measure"),
    "HH": _c("HH", "h", "glottal", "fricative", False, "hat"),
    "CH": _c("CH", "tʃ", "postalveolar", "affricate", False, "chair"),
    "JH": _c("JH", "dʒ", "postalveolar", "affricate", True, "jump"),
    "M": _c("M", "m", "bilabial", "nasal", True, "moon"),
    "N": _c("N", "n", "alveolar", "nasal", True, "nose"),
    "NG": _c("NG", "ŋ", "velar", "nasal", True, "sing"),
    "L": _c("L", "l", "alveolar", "lateral approximant", True, "leaf"),
    "R": _c("R", "r", "postalveolar", "approximant", True, "red"),
    "W": _c("W", "w", "labial-velar", "approximant", True, "web"),
    "Y": _c("Y", "j", "palatal", "approximant", True, "yes"),
    # vowels (General American broad transcription)
    "IY": _v("IY", "i", "high", "front", False, "see"),
    "IH": _v("IH", "ɪ", "near-high", "front", False, "sit"),
    "EY": _v("EY", "eɪ", "mid", "front", False, "cake", diphthong=True),
    "EH": _v("EH", "ɛ", "mid", "front", False, "bed"),
    "AE": _v("AE", "æ", "low", "front", False, "cat"),
    "AA": _v("AA", "ɑ", "low", "back", False, "father"),
    "AO": _v("AO", "ɔ", "mid", "back", True, "thought"),
    "OW": _v("OW", "oʊ", "mid", "back", True, "go", diphthong=True),
    "UH": _v("UH", "ʊ", "near-high", "back", True, "book"),
    "UW": _v("UW", "u", "high", "back", True, "moon"),
    "AH": _v("AH", "ʌ", "mid", "central", False, "cup"),
    "ER": _v("ER", "ɜr", "mid", "central", False, "bird", rhotic=True),
    "AY": _v("AY", "aɪ", "low", "front", False, "five", diphthong=True),
    "AW": _v("AW", "aʊ", "low", "central", False, "house", diphthong=True),
    "OY": _v("OY", "ɔɪ", "mid", "back", True, "boy", diphthong=True),
}

# Legal English syllable onsets used for maximal-onset syllabification.
_LEGAL_ONSETS = {
    tuple(o.split())
    for o in [
        "P R", "P L", "B R", "B L", "T R", "D R", "K R", "K L", "G R", "G L", "F R", "F L",
        "TH R", "SH R", "S P", "S T", "S K", "S M", "S N", "S L", "S W", "S F",
        "S P R", "S P L", "S T R", "S K R", "S K W", "S K L", "S K Y", "S P Y", "S M Y",
        "T W", "D W", "K W", "G W", "TH W", "P Y", "B Y", "K Y", "G Y", "F Y", "V Y",
        "M Y", "HH Y", "N Y", "L Y", "HH W",
    ]
}


def split_stress(phone: str) -> tuple[str, int | None]:
    """``"AH1" -> ("AH", 1)``; consonants return ``None`` stress."""
    base = phone.rstrip("012")
    stress = int(phone[len(base)]) if len(phone) > len(base) else None
    return base, stress


def base_phone(phone: str) -> str:
    return split_stress(phone)[0]


def is_vowel(phone: str) -> bool:
    return base_phone(phone) in VOWELS


def ipa_for(phone: str) -> str:
    """IPA symbol for an ARPAbet phone, taking stress into account for AH/ER."""
    base, stress = split_stress(phone)
    if base == "AH" and stress == 0:
        return "ə"
    if base == "ER" and stress == 0:
        return "ər"
    info = PHONEMES.get(base)
    if info is None:
        raise KeyError(f"Unknown ARPAbet phone: {phone}")
    return info.ipa


def to_ipa_list(arpabet: list[str]) -> list[str]:
    return [ipa_for(p) for p in arpabet]


def syllabify(arpabet: list[str]) -> list[list[str]]:
    """Split a pronunciation into syllables using the maximal onset principle."""
    vowel_idx = [i for i, p in enumerate(arpabet) if is_vowel(p)]
    if not vowel_idx:
        return [list(arpabet)]
    boundaries = [0]
    for a, b in zip(vowel_idx, vowel_idx[1:]):
        cluster = [base_phone(p) for p in arpabet[a + 1 : b]]
        # largest legal onset at the end of the intervocalic cluster
        split = len(cluster)  # default: everything goes to the coda
        for k in range(0, len(cluster) + 1):
            onset = tuple(cluster[k:])
            if len(onset) == 0 or len(onset) == 1 and onset[0] != "NG" or onset in _LEGAL_ONSETS:
                split = k
                break
        boundaries.append(a + 1 + split)
    boundaries.append(len(arpabet))
    return [arpabet[s:e] for s, e in zip(boundaries, boundaries[1:]) if e > s]


def syllable_count(arpabet: list[str]) -> int:
    return sum(1 for p in arpabet if is_vowel(p))


def to_ipa_string(arpabet: list[str], slashes: bool = True) -> str:
    """Broad IPA with stress marks at syllable onsets, e.g. ``/ˈbʌtərˌflaɪ/``."""
    out = []
    sylls = syllabify(arpabet)
    for syl in sylls:
        stress = next((split_stress(p)[1] for p in syl if is_vowel(p)), None)
        mark = "ˈ" if stress == 1 and len(sylls) > 1 else "ˌ" if stress == 2 else ""
        out.append(mark + "".join(ipa_for(p) for p in syl))
    s = "".join(out)
    return f"/{s}/" if slashes else s


def stress_pattern(arpabet: list[str]) -> list[int]:
    return [split_stress(p)[1] or 0 for p in arpabet if is_vowel(p)]


def feature_difference(a: str, b: str) -> list[str]:
    """Which articulatory dimensions differ between two phones (for diagnostics)."""
    ia, ib = PHONEMES.get(base_phone(a)), PHONEMES.get(base_phone(b))
    if ia is None or ib is None:
        return []
    if ia.kind != ib.kind:
        return ["vowel/consonant"]
    keys = ["place", "manner", "voiced"] if ia.kind == "consonant" else ["height", "backness", "rounded", "diphthong", "rhotic"]
    return [k for k in keys if ia.features.get(k) != ib.features.get(k)]


def phone_class(phone: str) -> str:
    """Coarse class used to group statistics: vowel, stop, fricative, ..."""
    info = PHONEMES[base_phone(phone)]
    if info.kind == "vowel":
        return "diphthong" if info.features["diphthong"] else "vowel"
    return info.features["manner"]
