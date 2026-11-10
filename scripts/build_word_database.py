#!/usr/bin/env python3
"""Build ``data/words.json`` from the curated list in ``data/source/words.csv``.

US pronunciations come from the CMU Pronouncing Dictionary (``pip install
cmudict``) unless overridden in the CSV.  A British (RP) variant is generated
with espeak-ng (``en-gb`` voice) when espeak-ng is installed and the result
differs from every US variant; it can also be given explicitly in the CSV.

Usage::

    python scripts/build_word_database.py            # writes data/words.json
    python scripts/build_word_database.py --check    # exit 1 if words.json is stale

The generated file is committed so that the application never needs CMUdict
or espeak-ng at runtime.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from speech_analysis.phoneme_analysis.lexicon import (  # noqa: E402
    cmudict_pronunciations,
    espeak_available,
    espeak_ipa,
    espeak_ipa_to_arpabet,
    strip_stress,
)
from speech_analysis.phoneme_analysis.phonemes import (  # noqa: E402
    PHONEMES,
    base_phone,
    ipa_for,
    is_vowel,
    split_stress,
    stress_pattern,
    syllabify,
    syllable_count,
    to_ipa_list,
    to_ipa_string,
)

SOURCE = ROOT / "data" / "source" / "words.csv"
OUTPUT = ROOT / "data" / "words.json"
ORDINALS = ["1st", "2nd", "3rd", "4th", "5th", "6th"]
CATEGORY_LABELS = {
    "simple_words": "Simple words",
    "s_sound": "S and Z sounds",
    "r_sound": "R sounds",
    "l_sound": "L sounds",
    "th_sound": "TH sounds",
    "sh_ch_j": "SH, CH and J sounds",
    "k_g_sound": "K and G sounds",
    "f_v_sound": "F and V sounds",
    "clusters": "Consonant clusters",
    "multisyllabic": "Multisyllabic words",
    "vowel_contrast": "Vowel contrasts",
}


def parse_variants(cell: str) -> list[list[str]]:
    return [v.split() for v in cell.split("|") if v.strip()] if cell and cell.strip() else []


def validate(arpabet: list[str], word: str) -> None:
    for p in arpabet:
        base, stress = split_stress(p)
        if base not in PHONEMES:
            raise ValueError(f"{word}: unknown phone {p}")
        if is_vowel(p) and stress is None:
            raise ValueError(f"{word}: vowel {p} needs a stress digit")


def ipa_seq(arpabet: list[str], idxs: list[int]) -> str:
    return "".join(ipa_for(arpabet[i]) for i in idxs)


def features_for(arpabet: list[str], focus: list[str]) -> list[dict]:
    feats: list[dict] = []
    n = len(arpabet)
    vowel_pos = [i for i, p in enumerate(arpabet) if is_vowel(p)]
    first_v, last_v = vowel_pos[0], vowel_pos[-1]

    onset = list(range(0, first_v))
    if onset:
        kind = "initial_cluster" if len(onset) > 1 else "initial_consonant"
        label = "Word-initial cluster" if len(onset) > 1 else "Word-initial consonant"
        feats.append({"type": kind, "positions": onset, "phonemes": [ipa_for(arpabet[i]) for i in onset],
                      "description": f"{label} /{ipa_seq(arpabet, onset)}/"})
    coda = list(range(last_v + 1, n))
    if coda:
        kind = "final_cluster" if len(coda) > 1 else "final_consonant"
        label = "Word-final cluster" if len(coda) > 1 else "Word-final consonant"
        feats.append({"type": kind, "positions": coda, "phonemes": [ipa_for(arpabet[i]) for i in coda],
                      "description": f"{label} /{ipa_seq(arpabet, coda)}/"})
    for a, b in zip(vowel_pos, vowel_pos[1:]):
        mid = list(range(a + 1, b))
        if len(mid) >= 2:
            feats.append({"type": "medial_cluster", "positions": mid, "phonemes": [ipa_for(arpabet[i]) for i in mid],
                          "description": f"Consonant sequence /{ipa_seq(arpabet, mid)}/ between syllables"})
    for i in vowel_pos:
        base, stress = split_stress(arpabet[i])
        if stress == 1:
            feats.append({"type": "stressed_vowel", "positions": [i], "phonemes": [ipa_for(arpabet[i])],
                          "description": f"Stressed vowel /{ipa_for(arpabet[i])}/"})
        if PHONEMES[base].features.get("diphthong"):
            feats.append({"type": "diphthong", "positions": [i], "phonemes": [ipa_for(arpabet[i])],
                          "description": f"Diphthong /{ipa_for(arpabet[i])}/ (gliding vowel)"})
        if base == "ER":
            feats.append({"type": "r_colored_vowel", "positions": [i], "phonemes": [ipa_for(arpabet[i])],
                          "description": f"R-coloured vowel /{ipa_for(arpabet[i])}/"})
    for f in focus:
        pos = [i for i, p in enumerate(arpabet) if base_phone(p) == f]
        if pos:
            feats.append({"type": "target_sound", "positions": pos, "phonemes": [ipa_for(arpabet[pos[0]])],
                          "description": f"Target sound /{ipa_for(arpabet[pos[0]])}/"})
    sylls = syllable_count(arpabet)
    pattern = stress_pattern(arpabet)
    if sylls > 1 and 1 in pattern:
        stress_txt = f", stress on the {ORDINALS[pattern.index(1)]} syllable"
    else:
        stress_txt = ""
    feats.append({"type": "syllables", "positions": [], "phonemes": [], "value": sylls,
                  "description": f"{sylls} syllable{'s' if sylls != 1 else ''}{stress_txt}"})
    return feats


def build() -> dict:
    rows = list(csv.DictReader(SOURCE.open(encoding="utf-8")))
    have_espeak = espeak_available()
    words = []
    seen = set()
    for idx, row in enumerate(rows, start=1):
        word = row["word"].strip()
        if word.lower() in seen:
            raise ValueError(f"duplicate word {word}")
        seen.add(word.lower())
        us = parse_variants(row.get("us_override", "")) or cmudict_pronunciations(word)
        if not us:
            raise ValueError(f"{word}: not in CMUdict; add us_override")
        # keep at most 3 US variants, deduplicated on phones (ignoring stress)
        uniq, keys = [], set()
        for v in us:
            k = strip_stress(v)
            if k not in keys:
                keys.add(k)
                uniq.append(v)
        us = uniq[:3]
        gb_cell = (row.get("gb_override") or "").strip()
        gb = [] if gb_cell.lower() == "none" else parse_variants(gb_cell)
        if not gb and gb_cell.lower() != "none" and have_espeak:
            gb = [espeak_ipa_to_arpabet(espeak_ipa(word.lower(), "en-gb"))]
        gb = [v for v in gb if strip_stress(v) not in keys]
        variants = []
        for j, v in enumerate(us):
            validate(v, word)
            variants.append({
                "id": "us" if j == 0 else f"us-{j + 1}",
                "accent": "General American" if j == 0 else "General American (alternate)",
                "arpabet": v,
                "ipa": to_ipa_string(v),
            })
        for v in gb[:1]:
            validate(v, word)
            variants.append({"id": "gb", "accent": "British (RP)", "arpabet": v, "ipa": to_ipa_string(v)})

        primary = variants[0]["arpabet"]
        focus = row["focus"].split()
        for f in focus:
            if f not in PHONEMES:
                raise ValueError(f"{word}: unknown focus phone {f}")
        target_sounds = []
        for f in focus:
            present = [p for p in primary if base_phone(p) == f]
            if present:
                s = ipa_for(present[0])
                if s not in target_sounds:
                    target_sounds.append(s)
        words.append({
            "id": idx,
            "word": word,
            "ipa": variants[0]["ipa"],
            "phonemes": to_ipa_list(primary),
            "arpabet": primary,
            "syllables": syllable_count(primary),
            "syllable_breakdown": [to_ipa_list(s) for s in syllabify(primary)],
            "stress_pattern": stress_pattern(primary),
            "difficulty": row["difficulty"].strip(),
            "category": row["category"].strip(),
            "category_label": CATEGORY_LABELS[row["category"].strip()],
            "target_sounds": target_sounds,
            "evaluation_features": features_for(primary, focus),
            "variants": variants,
            "notes": row.get("notes", "").strip() or None,
        })
    return {
        "schema_version": 1,
        "description": "Pronunciation practice words. Phonemes use ARPAbet (scoring) and broad IPA (display).",
        "sources": {
            "us_pronunciations": "CMU Pronouncing Dictionary (BSD-2-Clause) with manual overrides",
            "gb_pronunciations": "espeak-ng en-gb phonemizer (converted to ARPAbet), with manual overrides",
            "reference_audio": "Human recording in data/reference_audio/<word>.wav if present, otherwise neural TTS "
                               "(Piper) synthesised from each variant's phonemes, otherwise espeak-ng/browser TTS.",
        },
        "words": words,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if data/words.json differs from a fresh build")
    args = ap.parse_args()
    data = build()
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print("data/words.json is out of date; run scripts/build_word_database.py", file=sys.stderr)
            return 1
        print("data/words.json is up to date")
        return 0
    OUTPUT.write_text(text, encoding="utf-8")
    counts = {}
    for w in data["words"]:
        counts[w["difficulty"]] = counts.get(w["difficulty"], 0) + 1
    print(f"wrote {len(data['words'])} words to {OUTPUT.relative_to(ROOT)}: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
