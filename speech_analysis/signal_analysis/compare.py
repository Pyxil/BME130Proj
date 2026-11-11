"""Compare a recording with one standard: DTW alignment, then measures along the alignment.

1. Alignment. Dynamic time warping finds the frame-to-frame alignment that
   minimises the spectral (MFCC) distance, so speaking faster or slower is not
   penalised as a different sound. A small search over frequency-warp factors
   (vocal tract length normalisation) lets a child's or an adult's voice match.
2. Measures along the aligned path:
   * spectral distance - mean MFCC distance between aligned frames (which sounds);
   * loudness contour - correlation of the energy envelopes (rhythm, stress);
   * pitch contour - RMS difference of the aligned pitch tracks in semitones,
     each relative to its own median (melody, independent of voice pitch);
   * per part (syllable, or start / vowel / end) - local spectral distance,
     relative duration, loudness and high-frequency (hiss) energy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..scoring.dtw import dtw, local_tempo_deviation
from .features import SignalFeatures, frames_to_seconds
from .segments import Part

WARP_FACTORS = (0.88, 0.92, 0.96, 1.0, 1.04, 1.08, 1.12)


@dataclass
class Standard:
    """A reference recording of the word with its precomputed features and parts."""

    word: str
    variant_id: str
    source: str  # piper | human | espeak
    voice: str | None
    features: SignalFeatures
    parts: list[Part]
    syllables: int = 0  # loudness peaks found in the standard

    @property
    def label(self) -> str:
        return f"{self.source}:{self.voice}" if self.voice else self.source


@dataclass
class PartResult:
    part: Part
    distance: float  # mean spectral distance of the aligned frames
    user_start: int
    user_end: int
    relative_duration: float | None  # (user length / standard length) / whole-word ratio
    loudness_diff_db: float | None  # part loudness difference minus the whole-word difference
    high_band_diff_db: float | None  # same for 3.5-8 kHz energy (frication / hiss)


@dataclass
class Comparison:
    standard: Standard
    warp: float
    path: np.ndarray
    distance: float  # mean spectral distance along the path
    loudness_r: float | None
    pitch_rms_st: float | None
    pitch_pairs: int
    rate_ratio: float | None
    tempo_deviation: float
    parts: list[PartResult] = field(default_factory=list)


def _local_distance(X: np.ndarray, Y: np.ndarray, path: np.ndarray) -> np.ndarray:
    return np.linalg.norm(X[path[:, 0]] - Y[path[:, 1]], axis=1) / np.sqrt(X.shape[1])


def _pearson(a: np.ndarray, b: np.ndarray) -> float | None:
    if a.size < 5 or np.std(a) < 1e-6 or np.std(b) < 1e-6:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def align(user: SignalFeatures, std: SignalFeatures, warps=WARP_FACTORS) -> tuple[float, np.ndarray, float]:
    """Best (warp, path, mean distance) over the warp factors."""
    Y = std.spectral(1.0)
    best = None
    for a in warps:
        X = user.spectral(a)
        r = dtw(X, Y)
        if not len(r.path):
            continue
        d = float(_local_distance(X, Y, r.path).mean())
        if best is None or d < best[2]:
            best = (a, r.path, d)
    if best is None:
        raise ValueError("recording too short to align")
    return best


def compare(user: SignalFeatures, std: Standard, warps=WARP_FACTORS) -> Comparison:
    warp, path, distance = align(user, std.features, warps)
    s = std.features
    i, j = path[:, 0], path[:, 1]
    local = _local_distance(user.spectral(warp), s.spectral(1.0), path)

    loud_r = _pearson(user.energy_db[i], s.energy_db[j])

    both = np.isfinite(user.f0_hz[i]) & np.isfinite(s.f0_hz[j])
    pitch_rms, n_pitch = None, int(both.sum())
    if n_pitch >= 10:
        fu, fs = user.f0_hz[i][both], s.f0_hz[j][both]
        su, ss = 12 * np.log2(fu / np.median(fu)), 12 * np.log2(fs / np.median(fs))
        pitch_rms = float(np.sqrt(np.mean((su - ss) ** 2)))

    us, ue = user.speech_bounds()
    ss_, se = s.speech_bounds()
    rate = (ue - us) / max(1, se - ss_)
    in_speech = (j >= ss_) & (j < se)
    loud_offset = float(np.mean(user.energy_db[i][in_speech] - s.energy_db[j][in_speech])) if in_speech.any() else 0.0
    high_offset = float(np.mean(user.bands_db[i, 3][in_speech] - s.bands_db[j, 3][in_speech])) if in_speech.any() else 0.0

    parts = []
    for p in std.parts:
        m = (j >= p.start) & (j < p.end)
        if not m.any():
            parts.append(PartResult(p, float(local.mean()), 0, 0, None, None, None))
            continue
        ui = np.unique(i[m])
        uj = np.unique(j[m])
        rel = (len(ui) / len(uj)) / rate if rate > 0 else None
        parts.append(PartResult(
            part=p,
            distance=float(local[m].mean()),
            user_start=int(ui[0]),
            user_end=int(ui[-1]) + 1,
            relative_duration=None if rel is None else round(float(rel), 3),
            loudness_diff_db=round(float(np.mean(user.energy_db[i[m]] - s.energy_db[j[m]]) - loud_offset), 2),
            high_band_diff_db=round(float(np.mean(user.bands_db[i[m], 3] - s.bands_db[j[m], 3]) - high_offset), 2),
        ))

    return Comparison(
        standard=std, warp=warp, path=path, distance=distance,
        loudness_r=None if loud_r is None else round(loud_r, 4),
        pitch_rms_st=None if pitch_rms is None else round(pitch_rms, 3), pitch_pairs=n_pitch,
        rate_ratio=round(frames_to_seconds(ue - us) / max(1e-6, frames_to_seconds(se - ss_)), 3),
        tempo_deviation=round(local_tempo_deviation(path), 4), parts=parts,
    )


def pick_best(comparisons: list[Comparison]) -> Comparison:
    """The standard that explains the recording best: overall distance plus half the worst part's.

    Counting the worst part keeps a correct British "butterfly" from being judged
    against an American standard that happens to be close overall.
    """
    def key(c: Comparison) -> float:
        return c.distance + 0.5 * max((p.distance for p in c.parts), default=c.distance)
    return min(comparisons, key=key)


def mistake_contrasts(user: SignalFeatures, warp: float, correct: list[Standard],
                      mistakes: list) -> list[tuple[object, float]]:
    """For each (mistake, standards): mean over voices of d(correct) - d(mistake). Positive = closer to the mistake.

    Only voices that have both a correct standard (of the word's main pronunciation)
    and a mistake standard are used, so each difference compares one voice with itself.
    """
    by_voice: dict[str | None, float] = {}
    for s in correct:
        if s.source == "piper" and not s.variant_id.startswith("gb") and s.voice not in by_voice:
            by_voice[s.voice] = distance_only(user, s.features, warp)
    out = []
    for mistake, stds in mistakes:
        diffs = [by_voice[s.voice] - distance_only(user, s.features, warp) for s in stds if s.voice in by_voice]
        if diffs:
            out.append((mistake, float(np.mean(diffs))))
    return out


def distance_only(user: SignalFeatures, std: SignalFeatures, warp: float) -> float:
    """Mean aligned spectral distance (used to compare a recording with every word)."""
    X, Y = user.spectral(warp), std.spectral(1.0)
    r = dtw(X, Y)
    if not len(r.path):
        return float("inf")
    return float(_local_distance(X, Y, r.path).mean())
