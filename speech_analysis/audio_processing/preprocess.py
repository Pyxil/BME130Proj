"""Energy-based speech detection, quality gate, trimming and normalisation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import QualityThresholds
from ..contracts import QualityIssue, QualityReport

FRAME_MS = 25
HOP_MS = 10


def frame_rms_db(y: np.ndarray, sr: int, frame_ms: int = FRAME_MS, hop_ms: int = HOP_MS) -> np.ndarray:
    frame = max(1, int(sr * frame_ms / 1000))
    hop = max(1, int(sr * hop_ms / 1000))
    if len(y) < frame:
        y = np.pad(y, (0, frame - len(y)))
    windows = np.lib.stride_tricks.sliding_window_view(y, frame)[::hop]
    rms = np.sqrt(np.mean(windows.astype(np.float64) ** 2, axis=1) + 1e-12)
    return 20.0 * np.log10(rms + 1e-10)


def _fill_gaps(mask: np.ndarray, max_gap: int) -> np.ndarray:
    """Close short non-speech gaps (e.g. stop closures inside a word)."""
    out = mask.copy()
    idx = np.flatnonzero(mask)
    if idx.size < 2:
        return out
    for a, b in zip(idx, idx[1:]):
        if 1 < b - a <= max_gap + 1:
            out[a:b] = True
    return out


def _remove_islands(mask: np.ndarray, min_len: int) -> np.ndarray:
    out = mask.copy()
    n = len(mask)
    i = 0
    while i < n:
        if out[i]:
            j = i
            while j < n and out[j]:
                j += 1
            if j - i < min_len:
                out[i:j] = False
            i = j
        else:
            i += 1
    return out


@dataclass
class SpeechRegion:
    start: int  # samples
    end: int
    frame_mask: np.ndarray
    frame_db: np.ndarray
    threshold_db: float
    noise_db: float
    speech_db: float


def detect_speech(y: np.ndarray, sr: int) -> SpeechRegion | None:
    """Adaptive-threshold energy VAD returning the span from first to last speech frame."""
    db = frame_rms_db(y, sr)
    if db.size == 0:
        return None
    noise_floor = float(np.percentile(db, 10))
    peak = float(np.percentile(db, 99))
    threshold = max(noise_floor + 6.0, peak - 32.0, -62.0)
    mask = db > threshold
    hop = int(sr * HOP_MS / 1000)
    mask = _fill_gaps(mask, max_gap=int(250 / HOP_MS))
    mask = _remove_islands(mask, min_len=int(60 / HOP_MS))
    if not mask.any():
        return None
    frames = np.flatnonzero(mask)
    first, last = int(frames[0]), int(frames[-1])
    start = first * hop
    end = min(len(y), (last + 1) * hop + int(sr * FRAME_MS / 1000))
    speech_frames = db[mask]
    nonspeech = db[~mask]
    noise_db = float(np.median(nonspeech)) if nonspeech.size >= 10 else noise_floor
    speech_db = float(np.percentile(speech_frames, 90))
    return SpeechRegion(start, end, mask, db, threshold, noise_db, speech_db)


@dataclass
class PreparedAudio:
    """Result of preprocessing: trimmed, normalised audio plus a quality report."""

    audio: np.ndarray  # trimmed + normalised speech (80 ms padding) for DTW / timing
    sr: int
    raw: np.ndarray
    quality: QualityReport
    offset_s: float  # start of ``audio`` within ``raw``
    engine_audio: np.ndarray | None = None  # same gain, ~0.3 s of real context each side (for CTC models)
    engine_offset_s: float = 0.0


def prepare_audio(y: np.ndarray, sr: int, thresholds: QualityThresholds | None = None) -> PreparedAudio:
    """Quality-check, trim leading/trailing silence and normalise a recording."""
    t = thresholds or QualityThresholds()
    y = np.asarray(y, dtype=np.float32)
    y = y - float(np.mean(y)) if y.size else y  # remove DC offset
    duration = len(y) / sr if sr else 0.0
    issues: list[QualityIssue] = []
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    clipping = float(np.mean(np.abs(y) >= 0.985)) if y.size else 0.0

    if duration < t.min_duration_s:
        issues.append(QualityIssue(code="too_short", message="The recording is too short.", blocking=True))
    if duration > t.max_duration_s:
        issues.append(QualityIssue(code="too_long", message="Please record only the single word.", blocking=True))

    region = detect_speech(y, sr) if y.size else None
    if region is None or peak < 1e-4:
        db_all = frame_rms_db(y, sr) if y.size else np.zeros(1)
        if y.size and peak >= 1e-4 and db_all.max() - np.percentile(db_all, 10) > 12:
            issues.append(QualityIssue(code="too_quiet", message="The recording is very quiet. Move closer to the microphone or speak a little louder.", blocking=True))
        else:
            issues.append(QualityIssue(code="no_speech", message="No speech was detected. Check your microphone and try again.", blocking=True))
        report = QualityReport(
            usable=False, duration_s=round(duration, 3), speech_duration_s=0.0, speech_start_s=0.0,
            speech_end_s=0.0, peak_dbfs=_db(peak), clipping_ratio=round(clipping, 5), issues=issues,
        )
        return PreparedAudio(np.zeros(0, dtype=np.float32), sr, y, report, 0.0)

    pad = int(0.08 * sr)
    start, end = max(0, region.start - pad), min(len(y), region.end + pad)
    seg = y[start:end]
    speech_dur = (region.end - region.start) / sr
    rms_db = region.speech_db
    snr = region.speech_db - region.noise_db

    if speech_dur < t.min_speech_s:
        issues.append(QualityIssue(code="too_short", message="Only a very short sound was detected. Say the whole word.", blocking=True))
    if rms_db < t.min_rms_dbfs:
        issues.append(QualityIssue(code="too_quiet", message="The recording is very quiet. Move closer to the microphone or speak a little louder.", blocking=True))
    if clipping > t.max_clipping_ratio:
        issues.append(QualityIssue(code="clipping", message="The recording is distorted (too loud). Move slightly away from the microphone.", blocking=True))
    if snr < t.min_snr_db:
        issues.append(QualityIssue(code="noisy", message="There is too much background noise compared with your voice. Try a quieter place.", blocking=True))
    elif snr < t.warn_snr_db:
        issues.append(QualityIssue(code="noisy", message="Some background noise was detected; results may be less reliable.", blocking=False))

    # Incomplete recordings: the VAD still marks speech in the first/last frames,
    # i.e. speech continues past the edge of the recording.
    n_edge = max(1, int(round(t.edge_margin_s * 1000 / HOP_MS)))
    mask = region.frame_mask
    if mask[:n_edge].any() and region.frame_db[:n_edge].max() > region.threshold_db + 3.0:
        issues.append(QualityIssue(code="truncated_start", message="The start of the word may have been cut off. Wait a moment after pressing Record before speaking.", blocking=True))
    if mask[-n_edge:].any() and region.frame_db[-n_edge:].max() > region.threshold_db + 3.0:
        issues.append(QualityIssue(code="truncated_end", message="The end of the word may have been cut off. Keep recording until you have finished speaking.", blocking=True))

    # Normalise: 95th percentile frame level -> -20 dBFS, peak-limited.
    seg_db = frame_rms_db(seg, sr)
    level = float(np.percentile(seg_db, 95)) if seg_db.size else -20.0
    gain = 10 ** ((-20.0 - level) / 20.0)
    seg_peak = float(np.max(np.abs(seg))) if seg.size else 1.0
    gain = min(gain, 0.99 / max(seg_peak, 1e-6))
    seg = (seg * gain).astype(np.float32)
    ctx = int(0.3 * sr)
    e_start, e_end = max(0, region.start - ctx), min(len(y), region.end + ctx)
    engine_audio = np.clip(y[e_start:e_end] * gain, -1, 1).astype(np.float32)

    report = QualityReport(
        usable=not any(i.blocking for i in issues),
        duration_s=round(duration, 3),
        speech_duration_s=round(speech_dur, 3),
        speech_start_s=round(region.start / sr, 3),
        speech_end_s=round(region.end / sr, 3),
        rms_dbfs=round(rms_db, 1),
        peak_dbfs=_db(peak),
        snr_db=round(snr, 1),
        clipping_ratio=round(clipping, 5),
        issues=issues,
    )
    return PreparedAudio(seg, sr, y, report, start / sr, engine_audio, e_start / sr)


def _db(x: float) -> float:
    return round(20.0 * float(np.log10(max(x, 1e-10))), 1)
