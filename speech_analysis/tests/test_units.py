"""Unit tests that need no models: phonemes, lexicon, preprocessing, DTW, scoring, word database."""

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from speech_analysis.audio_processing import frame_rms_db, prepare_audio
from speech_analysis.config import AnalysisConfig
from speech_analysis.contracts import EngineInfo
from speech_analysis.phoneme_analysis.engines.base import EngineOutput, PhoneAssessment, VariantAssessment
from speech_analysis.phoneme_analysis.lexicon import espeak_ipa_to_arpabet
from speech_analysis.phoneme_analysis.phonemes import syllabify, syllable_count, to_ipa_list, to_ipa_string
from speech_analysis.phoneme_analysis.variation import accepted_alternatives
from speech_analysis.scoring.components import syllable_completeness, temporal_score
from speech_analysis.scoring.dtw import dtw
from speech_analysis.scoring.scorer import Evidence, build_result, describe_position

ROOT = Path(__file__).resolve().parents[2]
FIX = Path(__file__).resolve().parent / "fixtures"
WORDS = {w["word"]: w for w in json.loads((ROOT / "data" / "words.json").read_text(encoding="utf-8"))["words"]}


# ------------------------------------------------------------------ phonemes
def test_butterfly_ipa_matches_spec_example():
    arpa = ["B", "AH1", "T", "ER0", "F", "L", "AY2"]
    assert to_ipa_list(arpa) == ["b", "ʌ", "t", "ər", "f", "l", "aɪ"]
    assert to_ipa_string(arpa) == "/ˈbʌtərˌflaɪ/"
    assert syllable_count(arpa) == 3


@pytest.mark.parametrize("arpa,expected", [
    ("S T R AO1 B EH2 R IY0", [["S", "T", "R", "AO1"], ["B", "EH2"], ["R", "IY0"]]),
    ("B AH0 N AE1 N AH0", [["B", "AH0"], ["N", "AE1"], ["N", "AH0"]]),
    ("M AH1 NG K IY0", [["M", "AH1", "NG"], ["K", "IY0"]]),
])
def test_syllabify_maximal_onset(arpa, expected):
    assert syllabify(arpa.split()) == expected


def test_espeak_ipa_conversion_handles_british_variants():
    assert espeak_ipa_to_arpabet("təmˈɑːtəʊ") == ["T", "AH0", "M", "AA1", "T", "OW0"]
    assert espeak_ipa_to_arpabet("kˈɑː") == ["K", "AA1"]


def test_accent_rules_are_conservative():
    rabbit = ["R", "AE1", "B", "AH0", "T"]
    assert "W" not in accepted_alternatives(rabbit, 0)  # /w/ for /r/ must never be accepted
    assert "IH" in accepted_alternatives(rabbit, 3)  # unstressed schwa ~ /ɪ/
    water = ["W", "AO1", "T", "ER0"]
    assert "D" in accepted_alternatives(water, 2)  # flapped t
    assert "AA" in accepted_alternatives(["D", "AO1", "G"], 1)  # cot-caught merger


# -------------------------------------------------------------- word database
def test_word_database_is_complete_and_consistent():
    words = list(WORDS.values())
    assert len(words) >= 100
    assert {w["difficulty"] for w in words} == {"easy", "medium", "hard"}
    for w in words:
        assert w["phonemes"] == to_ipa_list(w["arpabet"]), w["word"]
        assert w["syllables"] == syllable_count(w["arpabet"]), w["word"]
        assert w["variants"][0]["arpabet"] == w["arpabet"]
        for v in w["variants"]:
            assert v["ipa"] == to_ipa_string(v["arpabet"])
        assert w["evaluation_features"], w["word"]


# -------------------------------------------------------------- preprocessing
@pytest.mark.parametrize("name,code", [
    ("quality_silence.wav", "no_speech"), ("quality_too_quiet.wav", "too_quiet"),
    ("quality_clipped.wav", "clipping"), ("quality_noisy.wav", "noisy"),
    ("quality_truncated_end.wav", "truncated_end"),
])
def test_quality_gate_rejects_bad_recordings(name, code):
    y, sr = sf.read(FIX / name, dtype="float32")
    p = prepare_audio(y, sr)
    assert not p.quality.usable
    assert code in {i.code for i in p.quality.issues if i.blocking}


def test_good_recording_is_trimmed_and_normalised():
    y, sr = sf.read(FIX / "rabbit_correct.wav", dtype="float32")
    p = prepare_audio(y, sr)
    assert p.quality.usable and p.quality.snr_db > 30
    assert len(p.audio) < len(y)  # silence trimmed
    assert np.max(np.abs(p.audio)) <= 0.99
    level = float(np.percentile(frame_rms_db(p.audio, 16000), 95))
    assert level == pytest.approx(-20.0, abs=1.5)  # loudness-normalised speech level
    assert p.engine_audio is not None and len(p.engine_audio) > len(p.audio)


# ------------------------------------------------------------------------ DTW
def test_dtw_properties():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(40, 12))
    stretched = np.repeat(X, 2, axis=0)
    other = rng.normal(size=(60, 12))
    assert dtw(X, X).cost == pytest.approx(0.0, abs=1e-6)
    assert dtw(X, stretched).cost < 0.05
    assert dtw(X, other).cost > 0.5


# --------------------------------------------------------------------- scoring
def _engine_output(word: dict, posteriors: list[float], alts=None) -> EngineOutput:
    arpa = word["arpabet"]
    phones = [
        PhoneAssessment(index=i, arpabet=p, posterior=post, strict_posterior=post,
                        best_alternative=(alts or {}).get(i, "AH0"), best_alternative_prob=1 - post,
                        deletion_prob=0.0, start_s=0.1 * i, end_s=0.1 * i + 0.1)
        for i, (p, post) in enumerate(zip(arpa, posteriors))
    ]
    va = VariantAssessment("us", arpa, -5.0, phones)
    return EngineOutput("test", "stub", va, [va], decoded_ipa=word["phonemes"], frames=100, frame_rate=100.0,
                        recognized_word=word["word"], recognized_matches_target=True)


def _evidence(word, eng):
    y, sr = sf.read(FIX / "rabbit_correct.wav", dtype="float32")
    q = prepare_audio(y, sr).quality
    syl = syllable_completeness(word["syllables"], word["syllables"], eng.best if eng else None)
    ts, timing = temporal_score(0.5, 0.5, 0.1)
    return Evidence(word, q, eng, EngineInfo(name="test", phoneme_level=True), None, syl, timing, ts)


def test_correct_production_can_be_mastered():
    w = WORDS["rabbit"]
    res = build_result(_evidence(w, _engine_output(w, [0.99] * 5)), AnalysisConfig(), None, "id", 1)
    assert res.status == "assessed" and res.rating == "mastered" and res.phonetically_accurate
    assert not res.identified_issues


def test_substitution_is_reported_and_blocks_mastery():
    w = WORDS["rabbit"]
    eng = _engine_output(w, [0.01, 0.99, 0.99, 0.99, 0.99], alts={0: "W"})
    res = build_result(_evidence(w, eng), AnalysisConfig(), None, "id", 1)
    assert res.rating != "mastered" and not res.phonetically_accurate
    issue = res.identified_issues[0]
    assert issue.type == "substitution" and issue.phoneme == "r" and issue.realized_as == "w"
    assert issue.id == "ph0-substitution"
    assert res.phoneme_scores[0].status in {"poor", "fair"}


def test_bad_quality_returns_retry_without_score():
    w = WORDS["rabbit"]
    y, sr = sf.read(FIX / "quality_silence.wav", dtype="float32")
    ev = Evidence(w, prepare_audio(y, sr).quality, None, EngineInfo(name="t", phoneme_level=True), None, None, None, None)
    res = build_result(ev, AnalysisConfig(), None, "id", 1)
    assert res.status == "retry_required" and res.overall_score is None and res.needs_retry


def test_describe_position():
    arpa = WORDS["butterfly"]["arpabet"]
    assert describe_position(arpa, 0) == "at the start of the word"
    assert describe_position(arpa, 3) == "in the second syllable"
    assert describe_position(arpa, 6) == "at the end of the word"


def test_missing_syllable_needs_model_and_acoustic_agreement():
    """'1 of 1 syllables missing' must not appear when the acoustic count finds the syllable."""
    from speech_analysis.calibration import PhoneCalibration

    w = WORDS["bread"]
    fair = PhoneCalibration({"global": {"x": [-10.0, 0.0], "y": [77.0, 77.0]}, "per_phone": {}}, "test")

    def run(detected_nuclei):
        eng = _engine_output(w, [0.01, 0.01, 0.03, 0.9])
        for ph in eng.best.phones:  # the model's best explanation: the sounds were deleted
            ph.best_alternative, ph.deletion_prob = None, 0.95
        ev = _evidence(w, eng)
        ev.syllables = syllable_completeness(1, detected_nuclei, eng.best)
        return build_result(ev, AnalysisConfig(), fair, "id", 1)

    heard = run(detected_nuclei=1)  # acoustics found the syllable -> no syllable message
    assert all(p.status == "fair" for p in heard.phoneme_scores)
    assert not any(i.type == "syllable_missing" for i in heard.identified_issues)
    gone = run(detected_nuclei=0)  # both signals agree -> reported
    assert any(i.type == "syllable_missing" for i in gone.identified_issues)
