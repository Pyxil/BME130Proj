"""Integration tests: full pipeline on committed fixture recordings.

Requires the Allosaurus model and Piper voices (``python scripts/download_models.py``).
Skipped automatically when they are absent, e.g. in the lightweight CI job.
Assertions are *relative* (an error scores lower than the correct production)
so they are robust to calibration updates.
"""

import json
from functools import lru_cache
from pathlib import Path

import pytest

from speech_analysis.config import AnalysisConfig
from speech_analysis.pipeline import PronunciationAnalyzer, load_words

FIX = Path(__file__).resolve().parent / "fixtures"
MANIFEST = json.loads((FIX / "manifest.json").read_text())
WORDS = {w["word"]: w for w in load_words()}


@lru_cache(maxsize=1)
def analyzer() -> PronunciationAnalyzer:
    cfg = AnalysisConfig.load()
    cfg.engine = "allosaurus"
    a = PronunciationAnalyzer(cfg)
    try:
        _ = a.engine
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"phoneme model not installed: {exc}")
    return a


def run(name: str):
    m = next(x for x in MANIFEST if x["file"] == name)
    return analyzer().analyze((FIX / name).read_bytes(), WORDS[m["word"]])


pytestmark = pytest.mark.model

PAIRS = [
    ("rabbit_correct.wav", "rabbit_r_as_w.wav", 0, "w"),
    ("leaf_correct.wav", "leaf_l_as_w.wav", 0, "w"),
    ("butterfly_correct_us.wav", "butterfly_vowel_error.wav", 1, "ɛ"),
    ("spoon_correct.wav", "spoon_cluster_reduced.wav", 0, None),
    ("banana_correct.wav", "banana_syllable_dropped.wav", 0, None),
]


@pytest.mark.parametrize("good,bad,pos,realised", PAIRS)
def test_error_scores_lower_than_correct(good, bad, pos, realised):
    g, b = run(good), run(bad)
    assert g.status == b.status == "assessed"
    assert b.phoneme_scores[pos].score < g.phoneme_scores[pos].score
    assert b.overall_score < g.overall_score
    assert b.rating != "mastered" and b.phonetically_accurate is False
    assert any(i.position == pos for i in b.identified_issues) or b.phoneme_scores[pos].status != "good"
    if realised:
        assert b.phoneme_scores[pos].likely_realization == realised


@pytest.mark.parametrize("name", ["rabbit_correct.wav", "butterfly_correct_us.wav", "spoon_correct.wav",
                                  "banana_correct.wav", "leaf_correct.wav"])
def test_correct_productions_score_well(name):
    r = run(name)
    assert r.status == "assessed" and r.overall_score >= 85
    assert r.word_recognized is True


def test_accent_variants_are_accepted():
    gb = run("butterfly_correct_gb.wav")
    assert gb.matched_variant.id == "gb"
    tomato = run("tomato_gb.wav")
    assert tomato.matched_variant.id == "us-2" and tomato.overall_score >= 80


@pytest.mark.parametrize("name", [m["file"] for m in MANIFEST if m["kind"] == "bad_quality"])
def test_bad_recordings_ask_for_retry(name):
    r = run(name)
    assert r.status == "retry_required" and r.overall_score is None and r.retry_reason
