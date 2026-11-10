#!/usr/bin/env python3
"""Calibrate the DTW-cost -> acoustic-similarity mapping.

For a sample of practice words we synthesise renditions with *held-out* TTS
speakers (not the reference voices), compute the pipeline's best DTW cost
against the references of (a) the same word and (b) a different word with
the same syllable count, and fit a 1-D logistic regression
P(same word | cost).  The midpoint/scale are written to
``speech_analysis/calibration/dtw.json``.

Limitation: synthetic speakers only.  Re-fit with real recordings when the
team has a consented dataset (see docs/validation.md).
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from speech_analysis.audio_processing import prepare_audio  # noqa: E402
from speech_analysis.audio_processing.io import resample  # noqa: E402
from speech_analysis.config import AnalysisConfig  # noqa: E402
from speech_analysis.pipeline import load_words  # noqa: E402
from speech_analysis.scoring.acoustic_similarity import acoustic_similarity  # noqa: E402
from speech_analysis.tts.piper import PiperVoice, arpabet_to_espeak_ipa  # noqa: E402
from speech_analysis.tts.reference import ReferenceAudioService  # noqa: E402

HELD_OUT = [("en_US-libritts_r-medium", s) for s in (5, 77, 150, 300, 520)] + [("en_GB-vctk-medium", s) for s in (10, 30)]


def main() -> int:
    random.seed(7)
    cfg = AnalysisConfig.load()
    refs = ReferenceAudioService(cfg)
    words = load_words()
    sample = random.sample(words, 36)
    voices = {}
    same, diff = [], []
    for w in sample:
        others = [o for o in words if o["syllables"] == w["syllables"] and o["word"] != w["word"]]
        other = random.choice(others)
        ref_same = refs.references_for_scoring(w["word"], w["variants"][:1])
        ref_diff = refs.references_for_scoring(other["word"], other["variants"][:1])
        for voice, sid in random.sample(HELD_OUT, 3):
            if voice not in voices:
                voices[voice] = PiperVoice.from_dir(cfg.model_dir / "piper" / voice)
            v = voices[voice]
            accent = "gb" if voice.startswith("en_GB") else "us"
            y = v.synthesize_ipa(arpabet_to_espeak_ipa(w["variants"][0]["arpabet"], accent), speaker_id=sid)
            y = resample(y, v.sample_rate, 16000)
            y = np.concatenate([np.zeros(4000, np.float32), y * 0.5, np.zeros(4000, np.float32)])
            p = prepare_audio(y, 16000)
            s1 = acoustic_similarity(p.audio, ref_same)
            s2 = acoustic_similarity(p.audio, ref_diff)
            if s1 and s2:
                same.append(s1.best_cost)
                diff.append(s2.best_cost)
        print(f"{w['word']:14s} same={np.mean(same[-3:]):.3f} diff({other['word']})={np.mean(diff[-3:]):.3f}")
    x = np.array(same + diff)
    yv = np.array([1] * len(same) + [0] * len(diff))

    def nll(params):
        a, b = params
        z = np.clip(a - b * x, -30, 30)
        p = 1 / (1 + np.exp(-z))
        return -np.mean(yv * np.log(p + 1e-9) + (1 - yv) * np.log(1 - p + 1e-9))

    res = minimize(nll, x0=[5.0, 10.0], method="Nelder-Mead")
    a, b = res.x
    midpoint, scale = float(a / b), float(1 / b)
    acc = float(np.mean(((a - b * x) > 0) == (yv == 1)))
    out = {
        "midpoint": round(midpoint, 4), "scale": round(scale, 4),
        "same_word_cost_mean": round(float(np.mean(same)), 4), "different_word_cost_mean": round(float(np.mean(diff)), 4),
        "pairs": int(len(x)), "classification_accuracy": round(acc, 3),
        "fitted_on": f"Piper TTS held-out speakers, {len(sample)} words, {len(x)} pairs (synthetic)",
    }
    path = ROOT / "speech_analysis" / "calibration" / "dtw.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
