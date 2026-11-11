"""One waveform -> aligned feature tracks (one value per 10 ms frame)."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from .dsp import (
    HOP,
    SR,
    autocorrelation_pitch,
    band_energies_db,
    cepstral_mean_variance_normalize,
    delta,
    fft_freqs,
    frame_signal,
    highpass,
    mel_filterbank,
    mfcc,
    power_spectrum,
    pre_emphasis,
    short_time_energy_db,
    spectral_centroid,
    zero_crossing_rate,
)


@lru_cache(maxsize=32)
def _filterbank(alpha: float) -> np.ndarray:
    return mel_filterbank(alpha=alpha)


@dataclass
class SignalFeatures:
    """Feature tracks of one recording, all on the same 10 ms frame grid."""

    duration_s: float
    energy_db: np.ndarray  # short-time energy (loudness envelope)
    zcr: np.ndarray  # zero-crossing rate
    centroid_hz: np.ndarray  # spectral centroid
    bands_db: np.ndarray  # (frames, 4) band energies, see dsp.BANDS
    vowel_db: np.ndarray  # 300-2500 Hz energy, used to find syllable nuclei
    f0_hz: np.ndarray  # pitch, NaN where unvoiced
    voicing: np.ndarray  # normalised autocorrelation peak (0..1)
    power: np.ndarray = field(repr=False)  # pre-emphasised power spectrum (frames, bins)
    _spectral: dict = field(default_factory=dict, repr=False)

    @property
    def n_frames(self) -> int:
        return len(self.energy_db)

    def spectral(self, alpha: float = 1.0) -> np.ndarray:
        """Per-frame feature vector used for alignment and spectral distance (cached per warp factor).

        * MFCC c1..c12, mean/variance normalised (which sound; c0, the level, is dropped);
        * their deltas (how the sound is changing);
        * loudness relative to the loudest frame, in units of 10 dB, weighted x2, so a
          missing sound (silence where the standard has a hiss) counts as a difference.
        The loudness term and its weight were chosen on held-out voices: it raised word
        identification from about 80% to 88% (docs/validation.md).
        """
        key = round(alpha, 4)
        if key not in self._spectral:
            C = cepstral_mean_variance_normalize(mfcc(self.power, _filterbank(key))[:, 1:])
            level = np.clip(self.energy_db - self.energy_db.max(), -50.0, 0.0)[:, None] / 10.0
            self._spectral[key] = np.hstack([C, delta(C), 2.0 * level])
        return self._spectral[key]

    def speech_bounds(self, floor_db: float = 30.0) -> tuple[int, int]:
        """First and last frame (exclusive end) within ``floor_db`` of the loudest frame."""
        active = np.flatnonzero(self.energy_db > self.energy_db.max() - floor_db)
        if active.size == 0:
            return 0, self.n_frames
        return int(active[0]), int(active[-1]) + 1


def extract(x: np.ndarray, sr: int = SR) -> SignalFeatures:
    """Run the signals-and-systems front end on one 16 kHz recording."""
    if sr != SR:
        raise ValueError(f"expected {SR} Hz audio, got {sr}")
    x = highpass(np.asarray(x, dtype=np.float64), sr)
    frames = frame_signal(x)
    freqs = fft_freqs()
    P = power_spectrum(frames)
    f0, voicing = autocorrelation_pitch(x)
    n = min(len(frames), len(f0))
    vowel = 10 * np.log10(P[:, (freqs >= 300) & (freqs <= 2500)].sum(axis=1) + 1e-12)
    return SignalFeatures(
        duration_s=len(x) / sr,
        energy_db=short_time_energy_db(frames)[:n],
        zcr=zero_crossing_rate(frames)[:n],
        centroid_hz=spectral_centroid(P, freqs)[:n],
        bands_db=band_energies_db(P, freqs)[:n],
        vowel_db=vowel[:n],
        f0_hz=f0[:n],
        voicing=voicing[:n],
        power=power_spectrum(frame_signal(pre_emphasis(x)))[:n],
    )


def frames_to_seconds(i: float) -> float:
    return float(i) * HOP / SR
