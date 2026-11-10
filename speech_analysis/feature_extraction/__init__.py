"""Acoustic feature extraction (MFCC, log-mel, F0, energy, syllable nuclei)."""

from __future__ import annotations

from dataclasses import dataclass, field

import librosa
import numpy as np
from scipy.signal import find_peaks

SR = 16000
N_FFT = 512  # 32 ms window
HOP = 160  # 10 ms hop
N_MELS = 40


def power_spectrogram(y: np.ndarray, sr: int = SR) -> np.ndarray:
    """|STFT|^2 with shape (freq_bins, frames)."""
    S = librosa.stft(y.astype(np.float32), n_fft=N_FFT, hop_length=HOP, win_length=400, center=True)
    return (np.abs(S) ** 2).astype(np.float64)


def warp_spectrum(P: np.ndarray, alpha: float) -> np.ndarray:
    """Linear frequency warp ``P'(f) = P(alpha * f)`` (vocal tract length normalisation).

    ``alpha > 1`` maps higher source frequencies down, which brings a speaker
    with a shorter vocal tract (higher formants) closer to a longer one.
    """
    if abs(alpha - 1.0) < 1e-6:
        return P
    n_bins = P.shape[0]
    src = np.arange(n_bins) * alpha
    lo = np.clip(np.floor(src).astype(int), 0, n_bins - 1)
    hi = np.clip(lo + 1, 0, n_bins - 1)
    frac = (src - lo)[:, None]
    out = (1 - frac) * P[lo] + frac * P[hi]
    out[src > n_bins - 1] = 1e-12
    return out


_MEL_FB: dict[int, np.ndarray] = {}


def _mel_fb(sr: int) -> np.ndarray:
    if sr not in _MEL_FB:
        _MEL_FB[sr] = librosa.filters.mel(sr=sr, n_fft=N_FFT, n_mels=N_MELS, fmin=60.0, fmax=sr / 2 - 200)
    return _MEL_FB[sr]


def log_mel(y: np.ndarray, sr: int = SR, alpha: float = 1.0, P: np.ndarray | None = None) -> np.ndarray:
    """Log-mel spectrogram (frames, N_MELS)."""
    P = power_spectrogram(y, sr) if P is None else P
    M = _mel_fb(sr) @ warp_spectrum(P, alpha)
    return np.log(M + 1e-10).T


def cmvn(X: np.ndarray) -> np.ndarray:
    """Per-utterance cepstral mean and variance normalisation."""
    mu = X.mean(axis=0, keepdims=True)
    sd = X.std(axis=0, keepdims=True) + 1e-8
    return (X - mu) / sd


def mfcc(
    y: np.ndarray, sr: int = SR, n_mfcc: int = 13, alpha: float = 1.0, deltas: bool = True,
    normalise: bool = True, P: np.ndarray | None = None,
) -> np.ndarray:
    """MFCC (c1..c12, dropping energy c0) with optional deltas, shape (frames, dims)."""
    L = log_mel(y, sr, alpha=alpha, P=P)
    C = librosa.feature.mfcc(S=L.T, n_mfcc=n_mfcc)[1:].T  # drop c0 (loudness)
    feats = [C]
    if deltas and C.shape[0] >= 9:
        feats.append(librosa.feature.delta(C.T, width=9).T)
    X = np.concatenate(feats, axis=1)
    return cmvn(X) if normalise else X


def energy_db(y: np.ndarray, sr: int = SR) -> np.ndarray:
    rms = librosa.feature.rms(y=y, frame_length=400, hop_length=HOP, center=True)[0]
    return 20 * np.log10(rms + 1e-10)


@dataclass
class PitchContour:
    f0: np.ndarray  # Hz, NaN when unvoiced
    voiced_prob: np.ndarray
    times: np.ndarray

    @property
    def voiced_fraction(self) -> float:
        return float(np.mean(np.isfinite(self.f0))) if self.f0.size else 0.0

    def summary(self) -> dict:
        v = self.f0[np.isfinite(self.f0)]
        if v.size < 3:
            return {"median_hz": None, "range_semitones": None, "voiced_fraction": round(self.voiced_fraction, 3)}
        lo, hi = np.percentile(v, [10, 90])
        return {
            "median_hz": round(float(np.median(v)), 1),
            "range_semitones": round(float(12 * np.log2(hi / lo)), 2),
            "voiced_fraction": round(self.voiced_fraction, 3),
        }


def pitch(y: np.ndarray, sr: int = SR) -> PitchContour:
    """F0 with probabilistic YIN (fmin 65 Hz, fmax 600 Hz covers adults and children)."""
    if len(y) < 1024:
        return PitchContour(np.full(0, np.nan), np.zeros(0), np.zeros(0))
    f0, _, vprob = librosa.pyin(y, fmin=65.0, fmax=600.0, sr=sr, frame_length=1024, hop_length=HOP)
    times = librosa.times_like(f0, sr=sr, hop_length=HOP)
    return PitchContour(f0, np.nan_to_num(vprob), times)


def vowel_band_db(y: np.ndarray, sr: int = SR, lo: float = 300.0, hi: float = 2500.0,
                  P: np.ndarray | None = None) -> np.ndarray:
    """Energy (dB) in the 300-2500 Hz band where vowel formants carry most energy."""
    P = power_spectrogram(y, sr) if P is None else P
    freqs = np.arange(P.shape[0]) * sr / N_FFT
    band = P[(freqs >= lo) & (freqs <= hi)].sum(axis=0)
    return 10 * np.log10(band + 1e-12)


def syllable_nuclei(y: np.ndarray, sr: int = SR, voiced_prob: np.ndarray | None = None,
                    min_dip_db: float = 3.0, rel_threshold_db: float = 20.0) -> tuple[int, list[float]]:
    """Count syllable nuclei as voiced peaks of vowel-band energy (after de Jong & Wempe, 2009).

    A nucleus is a local maximum of the smoothed 300-2500 Hz energy contour
    that is within ``rel_threshold_db`` of the loudest frame, separated from
    neighbouring peaks by a dip of at least ``min_dip_db`` and at least 100 ms
    away, and (if pitch is available) voiced.  Restricting the band suppresses
    fricative noise such as /s/.  This is a heuristic estimate used as
    supporting evidence only.
    """
    db = vowel_band_db(y, sr)
    if db.size < 5:
        return 0, []
    kernel = np.ones(5) / 5
    smooth = np.convolve(db, kernel, mode="same")
    floor = float(smooth.min())
    padded = np.concatenate([[floor], smooth, [floor]])
    peaks, _ = find_peaks(padded, height=float(smooth.max()) - rel_threshold_db, prominence=min_dip_db, distance=10)
    peaks = [p - 1 for p in peaks]
    if voiced_prob is not None and voiced_prob.size:
        n = len(voiced_prob)
        peaks = [p for p in peaks if p < n and voiced_prob[max(0, p - 3): p + 4].max() > 0.1]
    times = [float(p * HOP / sr) for p in peaks]
    return len(peaks), times


@dataclass
class AcousticFeatures:
    duration_s: float
    mfcc: np.ndarray
    pitch: PitchContour
    energy_db: np.ndarray
    syllable_nuclei: int
    nuclei_times: list[float] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "duration_s": round(self.duration_s, 3),
            "pitch": self.pitch.summary(),
            "energy_dynamic_range_db": round(float(np.percentile(self.energy_db, 95) - np.percentile(self.energy_db, 5)), 1)
            if self.energy_db.size else None,
            "syllable_nuclei": self.syllable_nuclei,
        }


def extract_features(y: np.ndarray, sr: int = SR) -> AcousticFeatures:
    pc = pitch(y, sr)
    n_nuclei, times = syllable_nuclei(y, sr, pc.voiced_prob)
    return AcousticFeatures(
        duration_s=len(y) / sr,
        mfcc=mfcc(y, sr),
        pitch=pc,
        energy_db=energy_db(y, sr),
        syllable_nuclei=n_nuclei,
        nuclei_times=times,
    )
