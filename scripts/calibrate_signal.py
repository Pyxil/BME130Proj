#!/usr/bin/env python3
"""Calibrate and validate the signal-comparison scorer on voices it has never heard.

Without recordings of real learners, the test material is synthetic: every
practice word is generated with Piper voices that are *not* used as standards
(different speakers, random speaking rate and voice variation), correctly and
with mistakes of two kinds:

* covered - common mistakes that have a minimal-pair standard (/w/ for /r/,
  /th/ for /s/, a dropped cluster consonant or final consonant, a common
  confusion of the stressed vowel ...);
* uncovered - mistakes with no minimal-pair standard (/k/ for /t/, a dropped
  weak syllable), to see how the overall similarity copes.

1. Calibration: the 0-100 mappings are anchored on the correct productions, so
   that a typical correct production by an unseen voice scores 95 and 90% of
   them score at least 85 ("good").
2. Validation (reported, not fitted):
   * word identification: is the recording closest to its own word's standards?
   * correct vs. mispronounced: AUC of the overall score, ratings, how often a
     covered mistake is named (and a correct recording wrongly gets a mistake),
     and whether the part containing the error is the one flagged.
3. The minimal-pair threshold is set so that 5% of correct recordings raise a
   false alarm (probability >= 0.5).

    python scripts/calibrate_signal.py              # writes speech_analysis/calibration/signal.json
    python scripts/calibrate_signal.py --quick      # a 30-word sample, no file written

Takes about 20-30 minutes for all words on a laptop CPU (Piper voices required).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from speech_analysis.audio_processing import prepare_audio  # noqa: E402
from speech_analysis.audio_processing.io import resample  # noqa: E402
from speech_analysis.calibration import SignalCalibration  # noqa: E402
from speech_analysis.phoneme_analysis.phonemes import is_vowel, syllabify, syllable_count  # noqa: E402
from speech_analysis.pipeline import PronunciationAnalyzer  # noqa: E402
from speech_analysis.scoring.components import syllable_completeness, temporal_score  # noqa: E402
from speech_analysis.signal_analysis.compare import compare, mistake_contrasts, pick_best  # noqa: E402
from speech_analysis.signal_analysis.features import extract, frames_to_seconds  # noqa: E402
from speech_analysis.signal_analysis.minimal_pairs import mistakes_for  # noqa: E402
from speech_analysis.signal_analysis.report import build_signal_result  # noqa: E402
from speech_analysis.signal_analysis.segments import syllable_nuclei  # noqa: E402
from speech_analysis.tts.piper import arpabet_to_espeak_ipa  # noqa: E402

OUT = ROOT / "speech_analysis" / "calibration" / "signal.json"
US_SPEAKERS = (120, 300, 500)  # en_US-libritts_r-medium speakers not used as standards (0, 40) or fixtures (12)
GB_SPEAKERS = (20, 40)  # en_GB-vctk-medium speakers not used as standards (3) or fixtures (5)
ERROR_SPEAKERS = (300, 700)

UNCOVERED_SUBS = {"T": "K", "D": "G", "P": "B", "B": "P", "M": "B", "N": "D"}  # no minimal-pair standard


def base(p: str) -> str:
    return p.rstrip("012")


def make_errors(arpa: list[str]) -> list[tuple[str, str, list[str], int]]:
    """(covered | uncovered, error type, realised ARPAbet, index of the changed sound) for a word."""
    out = []
    covered = mistakes_for(arpa)
    sub_ = next((m for m in covered if m.key.startswith("sub")), None)
    vowel = next((m for m in covered if m.key.startswith("vowel")), None)
    del_ = next((m for m in covered if m.kind == "deletion"), None)
    if sub_:
        out.append(("covered", "consonant substitution", list(sub_.arpabet), sub_.index))
    if vowel:
        out.append(("covered", "vowel change", list(vowel.arpabet), vowel.index))
    if del_:
        out.append(("covered", "cluster reduction" if del_.key == "cluster" else "final consonant deletion",
                    list(del_.arpabet), del_.index))
    for i, p in enumerate(arpa):
        if base(p) in UNCOVERED_SUBS:
            new = arpa.copy()
            new[i] = UNCOVERED_SUBS[base(p)]
            out.append(("uncovered", "other consonant substitution", new, i))
            break
    if syllable_count(arpa) >= 3:
        first = syllabify(arpa)[0]
        if not any(p.endswith("1") for p in first):
            out.append(("uncovered", "weak syllable deletion", arpa[len(first):], 0))
    return out


def part_of(arpa: list[str], idx: int) -> int:
    """Index of the part (as in signal_analysis.segments) that contains sound ``idx``."""
    sylls = syllabify(arpa)
    if len(sylls) > 1:
        k = 0
        for s, syl in enumerate(sylls):
            if idx < k + len(syl):
                return s
            k += len(syl)
        return len(sylls) - 1
    v = next((k for k, p in enumerate(arpa) if is_vowel(p)), 0)
    groups = [g for g in (range(0, v), range(v, v + 1), range(v + 1, len(arpa))) if len(g)]
    return next(n for n, g in enumerate(groups) if idx in g)


def anchors(values: np.ndarray, higher_is_better: bool) -> tuple[float, float]:
    """(value scoring 95, value scoring 85): the median and the 'worst 10%' of correct productions."""
    if higher_is_better:
        return float(np.median(values)), float(np.percentile(values, 10))
    return float(np.median(values)), float(np.percentile(values, 90))


def logistic_through(d95: float, d85: float) -> tuple[float, float]:
    """Midpoint and scale of 100 / (1 + exp((d - m) / s)) passing through (d95, 95) and (d85, 85)."""
    z95, z85 = np.log(1 / 0.95 - 1), np.log(1 / 0.85 - 1)
    s = (d85 - d95) / (z85 - z95)
    return d95 - z95 * s, s


def linear_through(v100: float, v85: float) -> tuple[float, float]:
    """(value scoring 0, value scoring 100) of a straight line through (v100, 100) and (v85, 85)."""
    return v100 - (v100 - v85) * 100 / 15, v100


def auc(pos: list[float], neg: list[float]) -> float:
    pos, neg = np.asarray(pos), np.asarray(neg)
    return float((np.sum(pos[:, None] > neg[None, :]) + 0.5 * np.sum(pos[:, None] == neg[None, :]))
                 / (len(pos) * len(neg)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--quick", action="store_true", help="30-word sample, print results, write nothing")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    an = PronunciationAnalyzer()
    words = an.vocabulary
    if args.quick:
        words = rng.sample(words, 30)
    t0 = time.perf_counter()
    an.standards.warm()
    print(f"standards ready for {an.standards.words_ready} words ({time.perf_counter() - t0:.0f}s)")
    us_voice = an.references._voice("en_US-libritts_r-medium")
    gb_voice = an.references._voice("en_GB-vctk-medium")
    if us_voice is None or gb_voice is None:
        sys.exit("Piper voices missing: run scripts/download_models.py")

    noise = np.random.default_rng(args.seed)

    def synth(voice, arpa, speaker, accent):
        y = voice.synthesize_ipa(arpabet_to_espeak_ipa(arpa, accent=accent), speaker_id=speaker,
                                 length_scale=rng.uniform(0.85, 1.25), noise_scale=0.667, noise_w=0.8)
        y = resample(y, voice.sample_rate, 16000)
        pad = noise.normal(0.0, 1e-3, 4800)  # 0.3 s of quiet room noise each side, like a real recording
        return np.concatenate([pad, y, noise.normal(0.0, 1e-3, 4800)])

    records = []
    skipped = 0
    for n, w in enumerate(words, 1):
        primary = w["variants"][0]["arpabet"]
        gb = next((v for v in w["variants"] if v["id"].startswith("gb")), w["variants"][0])["arpabet"]
        jobs = [("correct", None, us_voice, primary, s, "us", None) for s in US_SPEAKERS]
        jobs += [("correct", None, gb_voice, gb, s, "gb", None) for s in GB_SPEAKERS]
        for cover, etype, arpa, idx in make_errors(primary):
            jobs += [(f"error-{cover}", etype, us_voice, arpa, s, "us", part_of(primary, idx)) for s in ERROR_SPEAKERS]
        standards = an.standards.for_word(w)
        mistakes = an.standards.mistakes(w)
        for kind, etype, voice, arpa, spk, acc, epart in jobs:
            prepared = prepare_audio(synth(voice, arpa, spk, acc), 16000)
            if not prepared.quality.usable:
                skipped += 1
                continue
            user = extract(prepared.audio)
            best = pick_best([compare(user, s) for s in standards])
            ident = an.standards.identify(user, best.warp, top=3, target=w["word"])
            ident0 = an.standards.identify(user, best.warp, top=1, target=w["word"], syllable_penalty=0.0) \
                if kind == "correct" else None
            contrasts = mistake_contrasts(user, best.warp, standards, mistakes)
            variant = next((v for v in w["variants"] if v["id"] == best.standard.variant_id), w["variants"][0])
            syl = syllable_completeness(syllable_count(variant["arpabet"]), len(syllable_nuclei(user)))
            us_, ue = user.speech_bounds()
            ss, se = best.standard.features.speech_bounds()
            tscore, timing = temporal_score(frames_to_seconds(ue - us_), frames_to_seconds(se - ss),
                                            best.tempo_deviation)
            user.power = None  # free memory; the scorer needs only the tracks
            records.append(dict(word=w, kind=kind, etype=etype, epart=epart, comp=best, user=user, syl=syl,
                                contrasts=contrasts,
                                timing=timing, tscore=tscore, ident=ident, rank0=ident0.target_rank if ident0 else None,
                                quality=prepared.quality, n_std=len(standards)))
        if n % 10 == 0:
            print(f"  {n}/{len(words)} words, {len(records)} recordings ({time.perf_counter() - t0:.0f}s)")

    correct = [r for r in records if r["kind"] == "correct"]
    errors = [r for r in records if r["kind"].startswith("error")]
    covered = [r for r in errors if r["kind"] == "error-covered"]
    uncovered = [r for r in errors if r["kind"] == "error-uncovered"]
    d = np.array([r["comp"].distance for r in correct])
    pd = np.array([p.distance for r in correct for p in r["comp"].parts])
    lr = np.array([r["comp"].loudness_r for r in correct if r["comp"].loudness_r is not None])
    pr = np.array([r["comp"].pitch_rms_st for r in correct if r["comp"].pitch_rms_st is not None])
    dm, ds = logistic_through(*anchors(d, False))
    pm, ps = logistic_through(*anchors(pd, False))
    l0, l100 = linear_through(*anchors(lr, True))
    p100, p85 = anchors(pr, False)
    p0 = p100 + (p85 - p100) * 100 / 15
    # minimal pairs: 5% of correct recordings at probability >= 0.5, the median correct one at 0.05
    cmax = np.array([max(c for _, c in r["contrasts"]) for r in correct if r["contrasts"]])
    mm = float(np.percentile(cmax, 95))
    ms = max(1e-4, (mm - float(np.median(cmax))) / 2.944)
    cal = SignalCalibration(distance_midpoint=dm, distance_scale=ds, part_midpoint=pm, part_scale=ps,
                            loudness_low=l0, loudness_high=l100, pitch_good=p100, pitch_bad=p0,
                            mistake_midpoint=mm, mistake_scale=ms, source="calibration run")

    for r in records:
        r["result"] = build_signal_result(
            word=r["word"], quality=r["quality"], info=an.engine_info(), comp=r["comp"],
            standards_compared=r["n_std"], user=r["user"], syllables=r["syl"], timing=r["timing"],
            temporal=r["tscore"], ident=r["ident"], vocab_size=len(an.vocabulary), cfg=an.config, cal=cal,
            contrasts=r["contrasts"], analysis_id="calibration", processing_ms=0)

    def score(r):
        return r["result"].overall_score if r["result"].overall_score is not None else 0

    def rating_share(rs):
        out = {k: 0 for k in ("mastered", "satisfactory", "needs_practice", "inconclusive")}
        for r in rs:
            out[r["result"].rating or "inconclusive"] += 1
        return {k: round(v / max(1, len(rs)), 3) for k, v in out.items()}

    def flagged_right_part(r):
        sa = r["result"].signal_analysis
        if sa is None:
            return False
        worst = min(sa.parts, key=lambda p: p.similarity)
        return worst.index == r["epart"] and worst.status != "good"

    def named(r):
        """A mistake was reported at a sound (substitution, deletion, or "missing or different")."""
        return any(i.type in ("substitution", "deletion", "unclear_articulation")
                   for i in r["result"].identified_issues)

    by_type = {}
    for r in errors:
        by_type.setdefault(f"{r['etype']} ({r['kind'].split('-')[1]})", []).append(r)
    top1 = float(np.mean([r["ident"].target_rank == 1 for r in correct]))
    top3 = float(np.mean([(r["ident"].target_rank or 99) <= 3 for r in correct]))
    top1_nopen = float(np.mean([r["rank0"] == 1 for r in correct]))
    validation = {
        "correct_recordings": len(correct), "error_recordings": len(errors), "unusable_skipped": skipped,
        "words": len(words),
        "identification_top1": round(top1, 3), "identification_top3": round(top3, 3),
        "identification_top1_without_syllable_penalty": round(top1_nopen, 3),
        "auc_correct_vs_error": round(auc([score(r) for r in correct], [score(r) for r in errors]), 3),
        "auc_correct_vs_covered": round(auc([score(r) for r in correct], [score(r) for r in covered]), 3),
        "auc_correct_vs_uncovered": round(auc([score(r) for r in correct], [score(r) for r in uncovered]), 3),
        "mistake_named_covered": round(float(np.mean([named(r) for r in covered])), 3) if covered else None,
        "mistake_named_uncovered": round(float(np.mean([named(r) for r in uncovered])), 3) if uncovered else None,
        "mistake_false_alarm_correct": round(float(np.mean([named(r) for r in correct])), 3),
        "median_score_correct": float(np.median([score(r) for r in correct])),
        "median_score_error": float(np.median([score(r) for r in errors])) if errors else None,
        "ratings_correct": rating_share(correct), "ratings_error": rating_share(errors),
        "error_part_flagged": round(float(np.mean([flagged_right_part(r) for r in errors])), 3) if errors else None,
        "by_error_type": {k: {"n": len(v), "median_score": float(np.median([score(r) for r in v])),
                              "auc_vs_correct": round(auc([score(r) for r in correct], [score(r) for r in v]), 3),
                              "part_flagged": round(float(np.mean([flagged_right_part(r) for r in v])), 3),
                              "mistake_named": round(float(np.mean([named(r) for r in v])), 3)}
                          for k, v in sorted(by_type.items())},
    }
    fitted = {
        "fitted_on": f"Piper voices not used as standards ({len(correct)} correct recordings of {len(words)} "
                     f"words), {date.today().isoformat()}",
        "method": "Anchored on correct recordings: median -> 95, worst 10% -> 85 (see scripts/calibrate_signal.py)",
        "distance": {"midpoint": round(dm, 4), "scale": round(ds, 4)},
        "part": {"midpoint": round(pm, 4), "scale": round(ps, 4)},
        "loudness": {"low": round(l0, 4), "high": round(l100, 4)},
        "pitch": {"good": round(p100, 3), "bad": round(p0, 3)},
        "mistake": {"midpoint": round(mm, 4), "scale": round(ms, 4)},
        "validation": validation,
    }
    print(json.dumps(fitted, indent=2))
    if not args.quick:
        OUT.write_text(json.dumps(fitted, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
