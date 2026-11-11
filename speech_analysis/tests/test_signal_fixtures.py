"""Signal analysis on the committed fixture recordings, with real generated standards.

Needs the Piper voices (``python scripts/download_models.py --skip-allosaurus``); skipped without them.
The fixtures were generated with a voice that is not one of the standards. Assertions are relative
(a mistake scores lower than the correct word) so they survive recalibration. The vowel error in
butterfly_vowel_error.wav is not tested: vowel changes are a known blind spot of the signal comparison
(AUC 0.52 on held-out voices, docs/validation.md).
"""

import json
from functools import lru_cache
from pathlib import Path

import pytest

from speech_analysis.config import AnalysisConfig
from speech_analysis.pipeline import PronunciationAnalyzer, load_words

FIX = Path(__file__).resolve().parent / "fixtures"
MANIFEST = json.loads((FIX / "manifest.json").read_text(encoding="utf-8"))
ALL = load_words()
WORDS = {w["word"]: w for w in ALL}

pytestmark = pytest.mark.model


@lru_cache(maxsize=1)
def analyzer() -> PronunciationAnalyzer:
    fixture_words = {m["word"] for m in MANIFEST}
    vocab = [w for w in ALL if w["word"] in fixture_words] + [w for w in ALL[::5] if w["word"] not in fixture_words]
    a = PronunciationAnalyzer(AnalysisConfig(engine="signal"), vocabulary=vocab)
    if not a.references.available_voices():
        pytest.skip("Piper voices not installed (python scripts/download_models.py --skip-allosaurus)")
    for w in vocab:  # standards for word identification (mistake standards are made on demand)
        a.standards.for_word(w)
    return a


def run(name: str):
    m = next(x for x in MANIFEST if x["file"] == name)
    return analyzer().analyze((FIX / name).read_bytes(), WORDS[m["word"]])


PAIRS = [
    ("rabbit_correct.wav", "rabbit_r_as_w.wav"),
    ("spoon_correct.wav", "spoon_cluster_reduced.wav"),
    ("leaf_correct.wav", "leaf_l_as_w.wav"),
    ("banana_correct.wav", "banana_syllable_dropped.wav"),
]


@pytest.mark.parametrize("good,bad", PAIRS)
def test_mistake_scores_lower_than_correct(good, bad):
    g, b = run(good), run(bad)
    assert g.status == b.status == "assessed"
    assert g.engine.name == "signal-analysis" and g.phoneme_scores is None
    assert b.overall_score < g.overall_score
    assert b.rating != "mastered"


def test_gliding_is_named_by_the_minimal_pair_check():
    r = run("rabbit_r_as_w.wav")
    assert any(i.type == "substitution" and i.phoneme == "r" and i.realized_as == "w" for i in r.identified_issues)


def test_cluster_reduction_points_at_the_start_of_the_word():
    r = run("spoon_cluster_reduced.wav")
    worst = min(r.signal_analysis.parts, key=lambda p: p.similarity)
    assert worst.label == "the start of the word" and worst.status != "good"
    assert any(i.type in ("deletion", "unclear_articulation", "part_mismatch") for i in r.identified_issues)


@pytest.mark.parametrize("name", ["rabbit_correct.wav", "spoon_correct.wav", "butterfly_correct_us.wav",
                                  "strawberry_correct.wav", "leaf_correct.wav"])
def test_correct_recordings_do_well_and_are_identified(name):
    """No confident wrong claims on correct speech. By design about 5% of correct recordings get a
    borderline "may be missing or sound different" note (the minimal-pair false-alarm rate)."""
    r = run(name)
    assert r.rating in ("mastered", "satisfactory")
    assert r.signal_analysis.target_rank == 1
    assert not any(i.type in ("substitution", "deletion") for i in r.identified_issues)
