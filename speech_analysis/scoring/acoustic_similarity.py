"""Acoustic similarity to reference pronunciations via DTW on normalised MFCCs.

This is a *supplementary* signal (20% by default).  Raw DTW distance is not a
validated pronunciation score: it is sensitive to speaker, microphone and the
synthetic nature of TTS references.  Mitigations:

* per-utterance cepstral mean/variance normalisation (removes channel and
  loudness effects);
* c0 (energy) dropped;
* a small search over linear frequency-warp factors (vocal tract length
  normalisation), so children's and adults' voices can match a reference;
* several reference voices (male/female, US/UK); the best match is used.

The DTW cost is mapped to [0, 1] with a logistic curve whose parameters are
stored in the calibration file (see ``scripts/calibrate_dtw.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..feature_extraction import mfcc, power_spectrogram
from ..tts.reference import ReferenceAudio
from .dtw import dtw, local_tempo_deviation

WARP_FACTORS = (0.88, 0.92, 0.96, 1.0, 1.04, 1.08, 1.12)
# Defaults: logistic mapping of DTW cost to similarity (overridden by calibration).
DEFAULT_COST_MIDPOINT = 0.95
DEFAULT_COST_SCALE = 0.07


@dataclass
class SimilarityResult:
    similarity: float  # 0..1
    best_cost: float
    best_reference: str
    best_variant: str
    warp: float
    tempo_deviation: float
    per_reference: list[dict] = field(default_factory=list)


def cost_to_similarity(cost: float, midpoint: float = DEFAULT_COST_MIDPOINT, scale: float = DEFAULT_COST_SCALE) -> float:
    if not np.isfinite(cost):
        return 0.0
    return float(1.0 / (1.0 + np.exp((cost - midpoint) / scale)))


def acoustic_similarity(
    audio: np.ndarray,
    references: list[ReferenceAudio],
    variant_ids: set[str] | None = None,
    midpoint: float = DEFAULT_COST_MIDPOINT,
    scale: float = DEFAULT_COST_SCALE,
) -> SimilarityResult | None:
    refs = [r for r in references if variant_ids is None or r.variant_id in variant_ids] or references
    if not refs or audio.size < 1600:
        return None
    P = power_spectrogram(audio)
    user_feats = {a: mfcc(audio, alpha=a, P=P) for a in WARP_FACTORS}
    best = None
    per_ref = []
    for ref in refs:
        Y = mfcc(ref.audio)
        ref_best = None
        for a, X in user_feats.items():
            r = dtw(X, Y)
            if ref_best is None or r.cost < ref_best[0]:
                ref_best = (r.cost, a, r)
        cost, a, res = ref_best
        per_ref.append({"reference": f"{ref.source}:{ref.voice}", "variant": ref.variant_id,
                        "cost": round(cost, 4), "warp": a})
        if best is None or cost < best[0]:
            best = (cost, a, res, ref)
    cost, a, res, ref = best
    return SimilarityResult(
        similarity=round(cost_to_similarity(cost, midpoint, scale), 4),
        best_cost=round(cost, 4),
        best_reference=f"{ref.source}:{ref.voice}",
        best_variant=ref.variant_id,
        warp=a,
        tempo_deviation=round(local_tempo_deviation(res.path), 4),
        per_reference=per_ref,
    )
