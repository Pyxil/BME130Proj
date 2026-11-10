"""Syllable completeness and temporal characteristics.

Both are heuristic supporting measures (10% weight each by default) and are
documented as such in docs/architecture.md.
"""

from __future__ import annotations

import numpy as np

from ..contracts import SyllableReport, TimingReport
from ..phoneme_analysis.engines.base import VariantAssessment
from ..phoneme_analysis.phonemes import is_vowel


def syllable_completeness(
    expected: int,
    detected_nuclei: int | None,
    variant: VariantAssessment | None,
    vowel_present_min: float = 0.25,
) -> SyllableReport:
    """Combine model evidence (are the vowels there?) with an acoustic nucleus count."""
    vowels_present = None
    c_model = None
    if variant is not None:
        vowels = [p for p in variant.phones if is_vowel(p.arpabet)]
        present = [p for p in vowels if not (p.best_alternative is None and p.deletion_prob > 0.5)
                   and p.posterior + p.best_alternative_prob * (p.best_alternative is not None) >= vowel_present_min]
        vowels_present = len(present)
        c_model = vowels_present / max(1, len(vowels))
    c_acoustic = None
    if detected_nuclei is not None:
        tolerance = 1 if expected >= 3 else 0  # adjacent nuclei often merge in fluent speech
        c_acoustic = 1.0 if detected_nuclei >= expected - tolerance else detected_nuclei / max(1, expected)
    if c_model is not None and c_acoustic is not None:
        completeness = 0.7 * c_model + 0.3 * c_acoustic
    else:
        completeness = c_model if c_model is not None else c_acoustic
    return SyllableReport(
        expected=expected,
        detected_nuclei=detected_nuclei,
        vowels_present=vowels_present,
        completeness=None if completeness is None else round(float(completeness), 3),
    )


def temporal_score(speech_duration: float, reference_duration: float | None,
                   tempo_deviation: float | None) -> tuple[float | None, TimingReport]:
    """Score speaking rate and rhythm against the reference.

    Slow, careful speech is *not* penalised up to 2.2x the reference duration,
    because practising slowly is a common therapy strategy.
    """
    report = TimingReport(speech_duration_s=round(speech_duration, 3))
    if reference_duration is None or reference_duration <= 0:
        return None, report
    ratio = speech_duration / reference_duration
    report.reference_duration_s = round(reference_duration, 3)
    report.rate_ratio = round(ratio, 3)
    if ratio < 0.7:
        rate = 100.0 * (ratio / 0.7) ** 2
    elif ratio > 2.2:
        rate = 100.0 * (2.2 / ratio)
    else:
        rate = 100.0
    if tempo_deviation is not None:
        report.rhythm_deviation = round(tempo_deviation, 3)
        rhythm = 100.0 * float(np.exp(-max(0.0, tempo_deviation - 0.25) / 0.5))
        score = 0.6 * rate + 0.4 * rhythm
    else:
        score = rate
    return round(float(np.clip(score, 0, 100)), 1), report
