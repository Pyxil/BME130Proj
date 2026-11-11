"""Signal-analysis engine: signals-and-systems properties and scoring rules (no downloaded models needed)."""

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from scipy.signal import lfilter

from speech_analysis.audio_processing import prepare_audio
from speech_analysis.calibration import SignalCalibration
from speech_analysis.config import AnalysisConfig
from speech_analysis.contracts import EngineInfo
from speech_analysis.signal_analysis import dsp
from speech_analysis.signal_analysis.compare import Standard, align, compare, mistake_contrasts
from speech_analysis.signal_analysis.features import extract
from speech_analysis.signal_analysis.minimal_pairs import mistakes_for
from speech_analysis.signal_analysis.report import build_signal_result
from speech_analysis.signal_analysis.segments import segment

SR = 16000
FIX = Path(__file__).resolve().parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]
WORDS = {w["word"]: w for w in json.loads((ROOT / "data" / "words.json").read_text(encoding="utf-8"))["words"]}


def tone(f: float, dur: float = 0.5, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    return amp * np.sin(2 * np.pi * f * t)


def synthetic_vowel(f0: float, dur: float = 0.5) -> np.ndarray:
    """Glottal impulse train through three formant resonators (a source-filter model of a vowel)."""
    x = np.zeros(int(dur * SR))
    x[:: int(round(SR / f0))] = 1.0
    for fc, bw in ((700, 80), (1200, 90), (2600, 120)):
        r, th = np.exp(-np.pi * bw / SR), 2 * np.pi * fc / SR
        x = lfilter([1 - r], [1, -2 * r * np.cos(th), r * r], x)
    return x / np.max(np.abs(x)) * 0.5


def fixture_audio(name: str) -> np.ndarray:
    y, sr = sf.read(FIX / name, dtype="float32")
    return prepare_audio(y, sr).audio


def amplitude_at(x: np.ndarray, f: float) -> float:
    t = np.arange(len(x)) / SR
    return float(np.abs(np.dot(x, np.exp(-2j * np.pi * f * t))) * 2 / len(x))


def standard_from(name: str, word: str) -> Standard:
    f = extract(fixture_audio(name))
    return Standard(word, "us", "human", None, f, segment(f, WORDS[word]["arpabet"]))


# ---------------------------------------------------------------- dsp blocks
def test_highpass_removes_dc_and_hum_but_keeps_speech_band():
    x = 0.5 + tone(50) + tone(1000)
    y = dsp.highpass(x)
    assert abs(y.mean()) < 1e-3
    assert 20 * np.log10(amplitude_at(x, 50) / amplitude_at(y, 50)) > 20  # mains hum: > 20 dB down
    assert amplitude_at(y, 1000) == pytest.approx(amplitude_at(x, 1000), rel=0.02)


def test_pre_emphasis_is_a_first_order_fir_filter():
    impulse = np.zeros(5)
    impulse[0] = 1.0
    assert np.allclose(dsp.pre_emphasis(impulse, 0.97), [1.0, -0.97, 0, 0, 0])


def test_spectrum_of_a_tone_peaks_at_its_frequency():
    P = dsp.power_spectrum(dsp.frame_signal(tone(1000)))
    freqs = dsp.fft_freqs()
    assert freqs[np.argmax(P.mean(axis=0))] == pytest.approx(1000, abs=32)  # one FFT bin
    assert np.median(dsp.spectral_centroid(P, freqs)) == pytest.approx(1000, abs=60)


def test_zero_crossing_rate_separates_noise_from_voicing():
    noise = np.random.default_rng(0).normal(0, 0.1, SR)
    assert np.median(dsp.zero_crossing_rate(dsp.frame_signal(noise))) == pytest.approx(0.5, abs=0.05)
    assert np.median(dsp.zero_crossing_rate(dsp.frame_signal(tone(200)))) == pytest.approx(2 * 200 / SR, abs=0.01)


@pytest.mark.parametrize("f0", [110.0, 150.0, 220.0])
def test_autocorrelation_finds_the_pitch_of_a_vowel(f0):
    est, _ = dsp.autocorrelation_pitch(synthetic_vowel(f0))
    voiced = est[np.isfinite(est)]
    assert voiced.size > 0.8 * est.size
    assert np.median(voiced) == pytest.approx(f0, rel=0.03)


def test_mel_filterbank_triangles_cover_the_band():
    fb = dsp.mel_filterbank()
    assert fb.shape == (40, dsp.N_FFT // 2 + 1)
    assert fb.max() <= 1.0 + 1e-9 and np.all(fb.sum(axis=1) > 0)


def test_cepstral_normalisation_cancels_a_microphone_filter():
    """An LTI channel (here a strong tilt/resonance filter) barely changes the normalised features."""
    x = fixture_audio("rabbit_correct.wav").astype(np.float64)
    channel = lfilter([1.0, 0.6], [1.0, -0.5], x)  # a coloured "microphone"
    a, b, other = extract(x), extract(channel / np.max(np.abs(channel)) * 0.5), extract(fixture_audio("leaf_correct.wav"))
    same = align(a, b, warps=(1.0,))[2]
    different = align(a, other, warps=(1.0,))[2]
    assert same < 0.4 * different


def test_dtw_absorbs_slower_speech():
    import librosa

    x = fixture_audio("rabbit_correct.wav")
    slow = librosa.effects.time_stretch(x, rate=0.8)  # 25% longer, same pitch
    std = standard_from("rabbit_correct.wav", "rabbit")
    c_slow = compare(extract(slow), std)
    c_other = compare(extract(fixture_audio("leaf_correct.wav")), std)
    assert c_slow.distance < 0.75 * c_other.distance  # the phase vocoder itself adds some spectral artefacts
    assert c_slow.rate_ratio > 1.15  # measured as slower (phase-vocoder tails lengthen it a little more)


# -------------------------------------------------------------- word parts
def test_parts_follow_syllables_or_start_vowel_end():
    f = extract(fixture_audio("butterfly_correct_us.wav"))
    parts = segment(f, WORDS["butterfly"]["arpabet"])
    assert [p.label for p in parts] == ["the first syllable", "the second syllable", "the third syllable"]
    assert all(a.end <= b.start + 1 for a, b in zip(parts, parts[1:]))
    leaf = segment(extract(fixture_audio("leaf_correct.wav")), WORDS["leaf"]["arpabet"])
    assert [(p.label, p.phonemes) for p in leaf] == [
        ("the start of the word", ["l"]), ("the vowel", ["i"]), ("the end of the word", ["f"])]


def test_common_mistakes_for_a_word():
    keys = {m.key: m for m in mistakes_for(WORDS["rabbit"]["arpabet"])}
    assert keys["sub0-R-W"].arpabet[0] == "W" and keys["sub0-R-W"].realized == "W"
    spoon = mistakes_for(WORDS["spoon"]["arpabet"])
    assert any(m.key == "cluster" and m.arpabet == tuple(WORDS["spoon"]["arpabet"][1:]) for m in spoon)
    for word in WORDS.values():
        ms = mistakes_for(word["arpabet"])
        assert len(ms) <= 5 and len({m.arpabet for m in ms}) == len(ms)
    assert any(m.key.startswith("vowel") and m.realized == "EH" for m in mistakes_for(WORDS["rabbit"]["arpabet"]))


# ------------------------------------------------------------- report rules
def _result(user_name: str, contrasts=None):
    std = standard_from("rabbit_correct.wav", "rabbit")
    u = extract(fixture_audio(user_name))
    comp = compare(u, std)
    q = prepare_audio(*sf.read(FIX / user_name, dtype="float32")).quality
    return build_signal_result(
        word=WORDS["rabbit"], quality=q, info=EngineInfo(name="signal-analysis", phoneme_level=False),
        comp=comp, standards_compared=1, user=u, syllables=None, timing=None, temporal=None, ident=None,
        vocab_size=0, cfg=AnalysisConfig(), cal=SignalCalibration(), analysis_id="t", processing_ms=0,
        contrasts=contrasts)


def test_signal_result_contract():
    r = _result("rabbit_correct.wav")
    assert r.status == "assessed" and 0 <= r.overall_score <= 100 and r.phoneme_scores is None
    sa = r.signal_analysis
    assert [p.label for p in sa.parts] == ["the first syllable", "the second syllable"]
    c = sa.curves
    assert len(c.t) == len(c.user_db) == len(c.standard_db) and c.t == sorted(c.t)
    assert {x.name for x in r.components} >= {"spectral_similarity", "loudness_contour", "temporal"}


def test_closer_to_a_mistake_standard_is_reported_as_that_mistake():
    """Minimal pair: the recording equals the 'wabbit' standard, so the /r/ -> /w/ mistake is named."""
    u = extract(fixture_audio("rabbit_r_as_w.wav"))
    correct = Standard("rabbit", "us", "piper", "v1", extract(fixture_audio("rabbit_correct.wav")), [])
    mistake = next(m for m in mistakes_for(WORDS["rabbit"]["arpabet"]) if m.key == "sub0-R-W")
    wabbit = Standard("rabbit", "mistake", "piper", "v1", u, [])
    contrasts = mistake_contrasts(u, 1.0, [correct], [(mistake, [wabbit])])
    assert contrasts[0][1] > 0  # closer to the mistake
    r = _result("rabbit_r_as_w.wav", contrasts)
    sub = next(i for i in r.identified_issues if i.type == "substitution")
    assert (sub.phoneme, sub.realized_as, sub.position) == ("r", "w", 0)
    assert r.rating != "mastered"
    assert r.signal_analysis.mistakes_checked[0].probability > 0.9
