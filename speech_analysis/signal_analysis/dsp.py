"""Signals-and-systems building blocks for speech analysis (NumPy/SciPy only).

Every function is a textbook operation, written out explicitly so the analysis
can be followed step by step::

    x[n] -> high-pass -> pre-emphasis -> frames x window -> FFT -> |X_k(f)|^2
                                                                    |-> band energies, spectral centroid
                                                                    |-> mel filter bank -> log -> DCT = MFCC
    frames -> short-time energy, zero-crossing rate
    frames -> autocorrelation (computed with the FFT) -> pitch (F0)

Conventions: 16 kHz mono float signals; analysis frames are centred every
10 ms (``HOP``), so every feature below shares one time axis.
"""

from __future__ import annotations

import numpy as np
from scipy.fft import dct
from scipy.signal import butter, medfilt, sosfiltfilt

SR = 16000
FRAME = 400  # 25 ms analysis window
HOP = 160  # 10 ms between frames
N_FFT = 512  # FFT length (zero-padded): 31.25 Hz bin spacing
PITCH_FRAME = 640  # 40 ms: at least two periods of the lowest pitch (65 Hz)

# Frequency bands (Hz) with a rough phonetic meaning:
#   low   80-500    voicing, nasals, first formant of close vowels
#   mid   500-1500  first/second formants of most vowels
#   upper 1500-3500 second/third formants (where /r/, /l/, /w/ differ)
#   high  3500-8000 frication noise (/s/, /sh/, /f/, /th/) and bursts
BANDS = ((80.0, 500.0), (500.0, 1500.0), (1500.0, 3500.0), (3500.0, 8000.0))
BAND_NAMES = ("low", "mid", "upper", "high")


# ---------------------------------------------------------------- filtering
def highpass(x: np.ndarray, sr: int = SR, cutoff_hz: float = 70.0, order: int = 4) -> np.ndarray:
    """Zero-phase Butterworth high-pass filter.

    Removes DC offset, mains hum and rumble below ``cutoff_hz``, which carry no
    speech information. The filter runs forwards and backwards (``sosfiltfilt``),
    so its phase delay cancels and the output stays time-aligned with the input.
    """
    x = np.asarray(x, dtype=np.float64)
    sos = butter(order, cutoff_hz, btype="highpass", fs=sr, output="sos")
    if len(x) <= 3 * (2 * len(sos) + 1):  # too short for the filter's edge padding
        return x - x.mean()
    return sosfiltfilt(sos, x)


def pre_emphasis(x: np.ndarray, a: float = 0.97) -> np.ndarray:
    """``y[n] = x[n] - a x[n-1]``: a first-order FIR high-pass, ``H(z) = 1 - a z^-1``.

    Voiced speech falls off by about 6 dB per octave (glottal source plus lip
    radiation). Pre-emphasis flattens that tilt so high-frequency cues
    (fricatives, the second and third formants) are not swamped by the strong
    low frequencies.
    """
    x = np.asarray(x, dtype=np.float64)
    if x.size == 0:
        return x
    return np.append(x[0], x[1:] - a * x[:-1])


# ------------------------------------------------------------------ framing
def frame_signal(x: np.ndarray, frame_len: int = FRAME, hop: int = HOP) -> np.ndarray:
    """Overlapping frames (one per row), centred every ``hop`` samples.

    Frame ``i`` is centred on sample ``i * hop``: the signal is zero-padded by
    half a frame at each end, so frames of different lengths share one time axis.
    """
    x = np.asarray(x, dtype=np.float64)
    half = frame_len // 2
    x = np.pad(x, (half, half))
    n = 1 + max(0, (len(x) - frame_len) // hop)
    idx = np.arange(frame_len)[None, :] + hop * np.arange(n)[:, None]
    return x[idx]


def frame_times(n_frames: int, sr: int = SR, hop: int = HOP) -> np.ndarray:
    return np.arange(n_frames) * hop / sr


# ----------------------------------------------------------- time domain
def short_time_energy_db(frames: np.ndarray) -> np.ndarray:
    """Mean power of each frame in dB: the loudness envelope of the word."""
    return 10 * np.log10(np.mean(frames**2, axis=1) + 1e-12)


def zero_crossing_rate(frames: np.ndarray) -> np.ndarray:
    """Fraction of neighbouring samples that change sign.

    Noise-like fricatives (/s/, /f/) cross zero very often; voiced sounds, whose
    energy sits at low frequencies, cross rarely.
    """
    s = np.signbit(frames)
    return np.mean(s[:, 1:] != s[:, :-1], axis=1)


# ------------------------------------------------------- frequency domain
def fft_freqs(sr: int = SR, n_fft: int = N_FFT) -> np.ndarray:
    return np.fft.rfftfreq(n_fft, 1.0 / sr)


def power_spectrum(frames: np.ndarray, n_fft: int = N_FFT) -> np.ndarray:
    """``|FFT|^2`` of each Hamming-windowed frame, shape (frames, n_fft/2 + 1).

    Multiplying by a window before the FFT tapers the frame edges, which
    reduces spectral leakage (energy smearing into neighbouring bins).
    """
    w = np.hamming(frames.shape[1])
    X = np.fft.rfft(frames * w, n=n_fft, axis=1)
    return (np.abs(X) ** 2) / np.sum(w**2)


def spectral_centroid(P: np.ndarray, freqs: np.ndarray) -> np.ndarray:
    """Centre of mass of each frame's spectrum (Hz): high for hissy sounds, low for vowels."""
    return (P @ freqs) / (P.sum(axis=1) + 1e-12)


def band_energies_db(P: np.ndarray, freqs: np.ndarray, bands=BANDS) -> np.ndarray:
    """Energy in each frequency band (dB), shape (frames, len(bands))."""
    return np.stack(
        [10 * np.log10(P[:, (freqs >= lo) & (freqs < hi)].sum(axis=1) + 1e-12) for lo, hi in bands], axis=1)


def hz_to_mel(f):
    return 2595.0 * np.log10(1.0 + np.asarray(f) / 700.0)


def mel_to_hz(m):
    return 700.0 * (10.0 ** (np.asarray(m) / 2595.0) - 1.0)


def mel_filterbank(sr: int = SR, n_fft: int = N_FFT, n_mels: int = 40, fmin: float = 60.0,
                   fmax: float = 7800.0, alpha: float = 1.0) -> np.ndarray:
    """Triangular band-pass filters spaced evenly on the mel scale, shape (n_mels, bins).

    The mel scale is roughly linear below 1 kHz and logarithmic above, like the
    ear's frequency resolution. ``alpha`` warps the frequency axis (vocal tract
    length normalisation): the filters see the spectrum ``P(alpha f)``, so
    ``alpha > 1`` maps a shorter vocal tract's higher formants (a child's
    voice) down towards an adult's.
    """
    edges = mel_to_hz(np.linspace(hz_to_mel(fmin), hz_to_mel(fmax), n_mels + 2))
    f = fft_freqs(sr, n_fft) / alpha  # evaluating filters at f/alpha == filtering P(alpha f)
    fb = np.zeros((n_mels, f.size))
    for m in range(n_mels):
        lo, centre, hi = edges[m], edges[m + 1], edges[m + 2]
        rising = (f - lo) / (centre - lo)
        falling = (hi - f) / (hi - centre)
        fb[m] = np.maximum(0.0, np.minimum(rising, falling))
    return fb


def mfcc(P: np.ndarray, fb: np.ndarray, n_ceps: int = 13) -> np.ndarray:
    """Mel-frequency cepstral coefficients: DCT of the log mel-band energies.

    Speech is a source (the vibrating vocal folds or turbulent air) convolved
    with the vocal tract's impulse response. Taking the log turns that
    convolution into a sum, and the DCT then separates them: the first few
    coefficients describe the smooth spectral envelope (the shape of the vocal
    tract, i.e. which sound is being made), while pitch harmonics end up in the
    higher coefficients, which are discarded.
    """
    E = np.log(P @ fb.T + 1e-10)
    return dct(E, type=2, norm="ortho", axis=1)[:, :n_ceps]


def delta(C: np.ndarray, k: int = 2) -> np.ndarray:
    """Rate of change of each feature over time ("delta" coefficients).

    A least-squares slope over +/-``k`` frames: an FIR differentiator,
    ``d[t] = sum_n n (c[t+n] - c[t-n]) / (2 sum_n n^2)``. Deltas describe the
    transitions between sounds, not just the sounds themselves.
    """
    pad = np.pad(C, ((k, k), (0, 0)), mode="edge")
    num = sum(n * (pad[k + n: len(C) + k + n] - pad[k - n: len(C) + k - n]) for n in range(1, k + 1))
    return num / (2 * sum(n * n for n in range(1, k + 1)))


def cepstral_mean_variance_normalize(C: np.ndarray) -> np.ndarray:
    """Subtract each coefficient's mean over the utterance, then scale to unit variance.

    A microphone or room is (approximately) a linear time-invariant filter
    ``H(f)``. In the log spectrum, ``log|X(f) H(f)| = log|X(f)| + log|H(f)|``,
    so the channel adds the same constant to every frame's cepstrum: removing
    the time average cancels it. Scaling to unit variance also evens out
    differences in dynamic range between voices and recording levels.
    """
    mu = C.mean(axis=0, keepdims=True)
    sd = C.std(axis=0, keepdims=True) + 1e-8
    return (C - mu) / sd


# -------------------------------------------------------------------- pitch
def autocorrelation_pitch(x: np.ndarray, sr: int = SR, hop: int = HOP, frame_len: int = PITCH_FRAME,
                          fmin: float = 65.0, fmax: float = 600.0, threshold: float = 0.45,
                          silence_db: float = 35.0) -> tuple[np.ndarray, np.ndarray]:
    """Fundamental frequency (F0) per frame by the autocorrelation method.

    A periodic signal ``x[n] = x[n + T]`` has an autocorrelation
    ``r[k] = sum_n x[n] x[n+k]`` that peaks at lag ``k = T``. ``r`` is computed
    with the FFT (Wiener-Khinchin theorem: the autocorrelation is the inverse
    FFT of the power spectrum; zero-padding to twice the frame length avoids
    circular wrap-around). It is normalised by ``r[0]`` and by the window's own
    autocorrelation, so a perfectly periodic frame scores 1.

    A frame is voiced when its normalised peak exceeds ``threshold`` and it is
    within ``silence_db`` of the loudest frame. Returns ``(f0_hz, peak)`` with
    NaN for unvoiced frames.
    """
    frames = frame_signal(x, frame_len, hop)
    frames = frames - frames.mean(axis=1, keepdims=True)
    w = np.hanning(frame_len)
    n_fft = 1 << int(np.ceil(np.log2(2 * frame_len)))
    r = np.fft.irfft(np.abs(np.fft.rfft(frames * w, n_fft, axis=1)) ** 2, n_fft, axis=1)[:, :frame_len]
    rw = np.fft.irfft(np.abs(np.fft.rfft(w, n_fft)) ** 2, n_fft)[:frame_len]
    r = r / (r[:, :1] + 1e-12) / np.maximum(rw / rw[0], 1e-3)

    kmin, kmax = int(sr // fmax), int(np.ceil(sr / fmin))
    seg = r[:, kmin:kmax + 1]
    best = seg.max(axis=1)
    # Prefer the shortest lag whose peak is nearly as high as the best one: a
    # periodic signal also peaks at 2T, 3T ..., which would halve the pitch.
    near = seg >= 0.9 * best[:, None]
    k = np.argmax(near, axis=1)
    rows = np.arange(len(seg))
    while True:  # climb to the local maximum of that peak
        nxt = np.minimum(k + 1, seg.shape[1] - 1)
        up = seg[rows, nxt] > seg[rows, k]
        if not up.any():
            break
        k = np.where(up, nxt, k)
    peak = seg[rows, k]
    # parabolic interpolation around the peak for sub-sample lag precision
    left = seg[rows, np.maximum(k - 1, 0)]
    right = seg[rows, np.minimum(k + 1, seg.shape[1] - 1)]
    denom = left - 2 * peak + right
    shift = np.where(np.abs(denom) > 1e-12, 0.5 * (left - right) / denom, 0.0)
    lag = kmin + k + np.clip(shift, -0.5, 0.5)

    energy = short_time_energy_db(frames)
    voiced = (peak > threshold) & (energy > energy.max() - silence_db)
    f0 = np.where(voiced, sr / lag, np.nan)
    if f0.size >= 5:  # remove isolated octave jumps
        filled = np.where(np.isnan(f0), 0.0, f0)
        smooth = medfilt(filled, 5)
        f0 = np.where(voiced & (smooth > 0), smooth, np.where(voiced, f0, np.nan))
    return f0, peak
