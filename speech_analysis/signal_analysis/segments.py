"""Split a standard recording into parts (syllables, or start / vowel / end) for feedback.

Parts are located from the standard's own signal: syllable nuclei are peaks of
the 300-2500 Hz (vowel band) energy envelope, and syllables are split at the
energy dips between them. The expected sounds of each part come from the word
database; they label the part, they are not detected in the audio.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks

from ..phoneme_analysis.phonemes import is_vowel, syllabify, to_ipa_list
from .features import SignalFeatures

ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth")


@dataclass
class Part:
    index: int
    label: str  # e.g. "the first syllable", "the start of the word"
    phonemes: list[str]  # expected sounds in this part (IPA, from the dictionary)
    start: int  # frame range in the standard recording
    end: int


def syllable_nuclei(f: SignalFeatures, rel_db: float = 20.0, min_dip_db: float = 3.0) -> list[int]:
    """Frames of syllable nuclei: voiced peaks of the smoothed vowel-band energy."""
    if f.n_frames < 5:
        return []
    smooth = np.convolve(f.vowel_db, np.ones(5) / 5, mode="same")
    floor = float(smooth.min())
    padded = np.concatenate([[floor], smooth, [floor]])
    peaks, _ = find_peaks(padded, height=float(smooth.max()) - rel_db, prominence=min_dip_db, distance=10)
    peaks = [p - 1 for p in peaks]
    return [p for p in peaks if f.voicing[max(0, p - 3): p + 4].max() > 0.3]


def _proportional(start: int, end: int, weights: list[float]) -> list[int]:
    """Boundaries splitting [start, end) in proportion to ``weights``."""
    cum = np.cumsum([0.0] + list(weights))
    return [int(round(start + (end - start) * c / cum[-1])) for c in cum]


def _weight(arpa: list[str]) -> float:
    return sum(2.0 if is_vowel(p) else 1.0 for p in arpa)


def segment(f: SignalFeatures, arpabet: list[str]) -> list[Part]:
    start, end = f.speech_bounds()
    if end - start < 6:
        start, end = 0, f.n_frames
    syllables = syllabify(arpabet)
    nuclei = [p for p in syllable_nuclei(f) if start <= p < end]

    if len(syllables) == 1:
        sounds = syllables[0]
        v = next((k for k, p in enumerate(sounds) if is_vowel(p)), 0)
        onset, vowel, coda = sounds[:v], sounds[v:v + 1], sounds[v + 1:]
        groups = [(g, lab) for g, lab in ((onset, "the start of the word"), (vowel, "the vowel"),
                                          (coda, "the end of the word")) if g]
        edges = _proportional(start, end, [_weight(g) for g, _ in groups])
        if nuclei and len(groups) > 1:  # centre the vowel part on the vowel-band energy peak
            peak = max(nuclei, key=lambda p: f.vowel_db[p])
            k = next(i for i, (g, _) in enumerate(groups) if g is vowel)
            half = max(1, (edges[k + 1] - edges[k]) // 2)
            if k > 0:  # boundary between the start of the word and the vowel
                edges[k] = int(np.clip(peak - half, start + 2, peak))
            if k + 1 < len(groups):  # boundary between the vowel and the end of the word
                edges[k + 1] = int(np.clip(peak + half, peak + 1, end - 2))
        return [Part(i, lab, to_ipa_list(g), edges[i], max(edges[i + 1], edges[i] + 1))
                for i, (g, lab) in enumerate(groups)]

    if len(nuclei) == len(syllables):
        smooth = np.convolve(f.vowel_db, np.ones(5) / 5, mode="same")
        edges = [start] + [int(a + np.argmin(smooth[a:b])) for a, b in zip(nuclei[:-1], nuclei[1:])] + [end]
    else:
        edges = _proportional(start, end, [_weight(s) for s in syllables])
    parts = []
    for i, s in enumerate(syllables):
        label = f"the {ORDINALS[i]} syllable" if i < len(ORDINALS) else f"syllable {i + 1}"
        parts.append(Part(i, label, to_ipa_list(s), edges[i], max(edges[i + 1], edges[i] + 1)))
    return parts
