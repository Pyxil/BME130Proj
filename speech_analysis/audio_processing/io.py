"""Decoding of uploaded audio into mono float32 at 16 kHz."""

from __future__ import annotations

import io
import shutil
import subprocess
from math import gcd

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

TARGET_SR = 16000


class AudioDecodeError(ValueError):
    """Raised when the uploaded bytes are not decodable audio."""


def resample(y: np.ndarray, sr: int, target_sr: int = TARGET_SR) -> np.ndarray:
    if sr == target_sr:
        return y.astype(np.float32, copy=False)
    g = gcd(int(sr), int(target_sr))
    return resample_poly(y, target_sr // g, int(sr) // g).astype(np.float32)


def decode_audio(data: bytes, max_seconds: float = 30.0) -> tuple[np.ndarray, int]:
    """Decode WAV/FLAC/OGG (libsndfile) or, if ffmpeg is installed, WebM/MP4/MP3.

    Returns mono float32 samples in [-1, 1] at 16 kHz.  The browser client
    already uploads 16 kHz mono WAV, so ffmpeg is only a fallback for other
    clients.
    """
    if not data:
        raise AudioDecodeError("empty upload")
    y: np.ndarray | None = None
    sr = 0
    try:
        arr, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
        y = arr.mean(axis=1)
    except Exception:  # noqa: BLE001 - fall through to ffmpeg
        y = None
    if y is None:
        exe = shutil.which("ffmpeg")
        if exe is None:
            raise AudioDecodeError("unsupported audio format (send 16-bit PCM WAV)")
        proc = subprocess.run(
            [exe, "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-t", str(max_seconds),
             "-f", "f32le", "-ac", "1", "-ar", str(TARGET_SR), "pipe:1"],
            input=data, capture_output=True, timeout=30, check=False,
        )
        if proc.returncode != 0 or not proc.stdout:
            raise AudioDecodeError("could not decode audio")
        y = np.frombuffer(proc.stdout, dtype=np.float32).copy()
        sr = TARGET_SR
    if sr <= 0:
        raise AudioDecodeError("invalid sample rate")
    if len(y) > max_seconds * sr:
        y = y[: int(max_seconds * sr)]
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    return resample(y, sr, TARGET_SR), TARGET_SR


def encode_wav(y: np.ndarray, sr: int = TARGET_SR) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, np.clip(y, -1, 1), sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()
