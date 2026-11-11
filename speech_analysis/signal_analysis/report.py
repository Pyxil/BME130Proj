"""Turn a signal comparison into an :class:`AnalysisResult`: scores, parts, feedback issues, confidence.

Score = weighted mean of the available measures (``SignalWeights``):

* spectral similarity - aligned MFCC/loudness distance to the closest standard, calibrated to 0-100;
* loudness contour    - correlation of the energy envelopes (rhythm and stress);
* pitch contour       - aligned pitch movement in semitones (words with 2+ syllables);
* minimal pairs       - is the recording closer to a common mistake ("wabbit") than to the word?
* syllables           - loudness peaks counted in the recording vs. the expected syllables;
* timing              - duration vs. the standard (slow, careful speech is not penalised).

Each part of the word (syllable, or start / vowel / end) gets its own spectral
similarity; the part that differed most drives the feedback. The rating rules
mirror the phoneme scorer: "mastered" needs every part good, and a part far
below the standard means "needs practice", with the score capped to match.
"""

from __future__ import annotations

import numpy as np

from ..calibration import SignalCalibration
from ..config import AnalysisConfig
from ..contracts import (
    AnalysisResult,
    ComponentScore,
    EngineInfo,
    Issue,
    MatchedVariant,
    MistakeCheck,
    QualityReport,
    SignalAnalysis,
    SignalCurves,
    SignalPart,
    Strength,
    SyllableReport,
    TimingReport,
    WordMatch,
    WordRecognition,
)
from ..phoneme_analysis.phonemes import to_ipa_list
from ..scoring.scorer import describe_position
from .compare import Comparison
from .features import SignalFeatures, frames_to_seconds
from .segments import ORDINALS
from .standards import Identification

# Sounds whose noise shows up in the 3.5-8 kHz band
HISSY = {"s", "z", "ʃ", "ʒ", "f", "v", "θ", "ð", "tʃ", "dʒ", "h"}


def distance_score(d: float, midpoint: float, scale: float) -> float:
    if not np.isfinite(d):
        return 0.0
    return float(100.0 / (1.0 + np.exp((d - midpoint) / scale)))


def _linear(x: float, zero: float, hundred: float) -> float:
    return float(100.0 * np.clip((x - zero) / (hundred - zero), 0.0, 1.0))


def _cap(label: str) -> str:
    return label[:1].upper() + label[1:]


def _status(sim: float, cfg: AnalysisConfig) -> str:
    s = cfg.signal
    return "good" if sim >= s.part_good else "fair" if sim >= s.part_fair else "poor"


def _part_reasons(p: SignalPart) -> list[str]:
    reasons = []
    if p.relative_duration is not None and p.relative_duration < 0.6:
        reasons.append("It was much shorter than in the example, so a sound may be missing.")
    elif p.relative_duration is not None and p.relative_duration > 1.8:
        reasons.append("It was much longer than in the example.")
    hissy = any(ph in HISSY for ph in p.phonemes)
    if p.high_band_diff_db is not None:
        if hissy and p.high_band_diff_db <= -8:
            reasons.append("It had much less of the hissing sound than the example.")
        elif not hissy and p.high_band_diff_db >= 8:
            reasons.append("It had more hissing or breathy noise than the example.")
    if p.loudness_diff_db is not None and p.loudness_diff_db <= -6:
        reasons.append("It was quieter, compared with the rest of the word, than in the example.")
    return reasons[:2]


def _curves(user: SignalFeatures, comp: Comparison, n: int = 120) -> SignalCurves:
    s = comp.standard.features
    first: dict[int, int] = {}
    for i, j in comp.path:
        first.setdefault(int(j), int(i))
    js = np.unique(np.linspace(0, s.n_frames - 1, min(n, s.n_frames)).round().astype(int))
    ui = np.array([first.get(int(j), 0) for j in js])

    def rel_db(x: np.ndarray) -> np.ndarray:
        return np.clip(x - x.max(), -60.0, 0.0)

    def semitones(f0: np.ndarray, idx: np.ndarray) -> list[float | None]:
        v = f0[np.isfinite(f0)]
        if v.size < 3:
            return [None] * len(idx)
        med = float(np.median(v))
        return [None if not np.isfinite(f0[k]) else round(float(12 * np.log2(f0[k] / med)), 2) for k in idx]

    span = max(1, s.n_frames - 1)
    return SignalCurves(
        t=[round(float(j) / span, 4) for j in js],
        user_db=[round(float(v), 1) for v in rel_db(user.energy_db)[ui]],
        standard_db=[round(float(v), 1) for v in rel_db(s.energy_db)[js]],
        user_pitch_st=semitones(user.f0_hz, ui),
        standard_pitch_st=semitones(s.f0_hz, js),
        part_edges=[round(p.part.start / span, 4) for p in comp.parts[1:]],
    )


def build_signal_result(
    *, word: dict, quality: QualityReport, info: EngineInfo, comp: Comparison, standards_compared: int,
    user: SignalFeatures, syllables: SyllableReport | None, timing: TimingReport | None,
    temporal: float | None, ident: Identification | None, vocab_size: int, cfg: AnalysisConfig,
    contrasts: list | None = None,
    cal: SignalCalibration, analysis_id: str, processing_ms: int,
) -> AnalysisResult:
    sc, w = cfg.signal, cfg.signal.weights
    n_syl = syllables.expected if syllables else len(comp.parts)

    spectral = distance_score(comp.distance, cal.distance_midpoint, cal.distance_scale)
    loud = None if comp.loudness_r is None else _linear(comp.loudness_r, cal.loudness_low, cal.loudness_high)
    pitch = None
    if comp.pitch_rms_st is not None and n_syl >= 2:
        pitch = _linear(comp.pitch_rms_st, cal.pitch_bad, cal.pitch_good)
    syl_score = None if not syllables or syllables.completeness is None else 100 * syllables.completeness
    checks = [(m, c, float(1.0 / (1.0 + np.exp(-(c - cal.mistake_midpoint) / cal.mistake_scale))))
              for m, c in (contrasts or [])]
    p_max = max((pr for _, _, pr in checks), default=None)
    components = [
        ComponentScore(name="spectral_similarity", score=round(spectral, 1), weight=w.spectral_similarity,
                       available=True, details={"distance": round(comp.distance, 4), "standard": comp.standard.label,
                                                "warp": comp.warp, "standards_compared": standards_compared,
                                                "calibration": cal.source}),
        ComponentScore(name="minimal_pair_contrast", score=None if p_max is None else round(100 * (1 - p_max), 1),
                       weight=w.minimal_pair_contrast, available=p_max is not None,
                       details={"mistakes_checked": len(checks),
                                "highest_probability": None if p_max is None else round(p_max, 3)}),
        ComponentScore(name="loudness_contour", score=None if loud is None else round(loud, 1),
                       weight=w.loudness_contour, available=loud is not None,
                       details={"correlation": comp.loudness_r}),
        ComponentScore(name="pitch_contour", score=None if pitch is None else round(pitch, 1),
                       weight=w.pitch_contour, available=pitch is not None,
                       details={"rms_semitones": comp.pitch_rms_st, "voiced_frames": comp.pitch_pairs,
                                "used_for": "words with 2 or more syllables"}),
        ComponentScore(name="syllable_completeness", score=None if syl_score is None else round(syl_score, 1),
                       weight=w.syllable_completeness, available=syl_score is not None,
                       details={} if not syllables else syllables.model_dump()),
        ComponentScore(name="temporal", score=temporal, weight=w.temporal, available=temporal is not None,
                       details={} if not timing else timing.model_dump()),
    ]
    avail = [c for c in components if c.available and c.score is not None]
    overall = round(sum(c.score * c.weight for c in avail) / sum(c.weight for c in avail))

    parts: list[SignalPart] = []
    for pr in comp.parts:
        sim = int(round(distance_score(pr.distance, cal.part_midpoint, cal.part_scale)))
        parts.append(SignalPart(
            index=pr.part.index, label=pr.part.label, phonemes=pr.part.phonemes, similarity=sim,
            status=_status(sim, cfg), start_s=round(frames_to_seconds(pr.user_start), 3),
            end_s=round(frames_to_seconds(pr.user_end), 3), relative_duration=pr.relative_duration,
            loudness_diff_db=pr.loudness_diff_db, high_band_diff_db=pr.high_band_diff_db))

    # ------------------------------------------------------------ confidence
    q = quality
    factors: dict[str, float] = {}
    snr = q.snr_db if q.snr_db is not None else cfg.quality.warn_snr_db
    lo, hi = cfg.quality.min_snr_db, cfg.quality.warn_snr_db
    factors["recording_quality"] = float(np.clip(0.5 + 0.5 * (snr - lo) / max(1e-6, hi - lo), 0.5, 1.0))
    if any(not i.blocking for i in q.issues):
        factors["recording_quality"] *= 0.9
    factors["standards"] = 0.7 if comp.standard.source == "espeak" else 1.0 if standards_compared >= 2 else 0.85
    complete = ident is not None and vocab_size > 0 and ident.words_compared >= 0.8 * vocab_size
    if complete and ident.target_rank is not None:
        if ident.target_rank == 1:
            factors["word_match"] = 1.0
        elif overall >= cfg.rating.satisfactory:
            factors["word_match"] = 0.6  # close to the standard, yet another word matched better
        else:
            factors["word_match"] = 0.85  # consistently far from the standard: a low score is credible
    if timing and timing.rate_ratio is not None:
        r = timing.rate_ratio
        factors["duration_plausibility"] = 1.0 if 0.4 <= r <= 3.5 else 0.6 if 0.25 <= r <= 5.0 else 0.35
    factors = {k: round(v, 3) for k, v in factors.items()}
    confidence = float(np.prod(list(factors.values())))
    ct = cfg.confidence
    label = "high" if confidence >= ct.high_at_or_above else "medium" if confidence >= ct.low_below else "low"

    variant = next((v for v in word["variants"] if v["id"] == comp.standard.variant_id), word["variants"][0])
    recognized = ident.ranked[0][0] if ident and ident.ranked else None
    matches = None if not complete or ident.target_rank is None else ident.target_rank == 1
    base = dict(
        analysis_id=analysis_id, word=word["word"], word_id=word.get("id"), quality=quality, engine=info,
        processing_ms=processing_ms, confidence=round(confidence, 3), confidence_label=label,
        confidence_factors=factors, components=components, syllables=syllables, timing=timing,
        matched_variant=MatchedVariant(id=variant["id"], accent=variant["accent"], ipa=variant["ipa"],
                                       arpabet=variant["arpabet"]),
        acoustic_similarity=round(spectral / 100, 4), word_recognized=matches, recognized_word=recognized,
        recognition=WordRecognition(closest_word=recognized, matches_target=matches),
    )
    if confidence < ct.inconclusive_below:
        return AnalysisResult(
            **base, status="inconclusive", needs_retry=True, overall_score=None,
            retry_reason="We couldn't analyse this recording reliably. Please say the word once more, clearly, "
                         "in a quiet place.")

    # -------------------------------------------------- rating and score caps
    detected = sorted((x for x in checks if x[2] >= sc.mistake_report_probability), key=lambda x: -x[2])
    all_good = all(p.status == "good" for p in parts) and not detected
    strong_error = any(p.similarity < cfg.rating.strong_error_below for p in parts) \
        or any(pr >= sc.mistake_strong_probability for _, _, pr in detected)
    cap = None
    if cfg.rating.cap_scores:
        if strong_error and overall >= cfg.rating.satisfactory:
            overall, cap = cfg.rating.satisfactory - 1, "a part of the word was far from the standard"
        elif not all_good and overall >= cfg.rating.mastered:
            overall, cap = cfg.rating.mastered - 1, "not every part of the word matched the standard well"
    if cap:
        components[0].details["score_cap"] = cap
    if overall >= cfg.rating.mastered and all_good:
        rating = "mastered"
    elif overall < cfg.rating.satisfactory or strong_error:
        rating = "needs_practice"
    else:
        rating = "satisfactory"

    # ------------------------------------------------------ issues, strengths
    issues: list[Issue] = []
    arpa = word["variants"][0]["arpabet"]

    def ipa(a: str | None) -> str | None:
        return None if a is None else to_ipa_list([a])[0]

    # all candidate mistakes at each sound, most likely first: a near tie (even with a candidate just
    # below the reporting threshold) means "missing or different", not a confident specific claim
    by_position: dict[int, list] = {}
    for x in sorted(checks, key=lambda x: -x[2]):
        by_position.setdefault(x[0].index, []).append(x)
    for group in [by_position[i] for i in dict.fromkeys(m.index for m, _, _ in detected)][:2]:
        m, c, pr = group[0]
        where = describe_position(arpa, m.index)
        severity = "major" if pr >= sc.mistake_strong_probability else "moderate"
        evidence = {"method": "minimal-pair comparison", "probability": round(pr, 3), "contrast": round(c, 4)}
        if len(group) > 1 and pr - group[1][2] < 0.15:
            # two mistakes at the same sound fit almost equally well: say so instead of picking one
            issues.append(Issue(
                id=f"ph{m.index}-unclear", type="unclear_articulation", severity=severity, phoneme=ipa(m.expected),
                position=m.index, message=f"The /{ipa(m.expected)}/ sound {where} may be missing or sound different "
                                          "from the example.",
                evidence={**evidence, "candidates": [x[0].key for x in group]}))
            continue
        msg = (f"The /{ipa(m.expected)}/ sound {where} may have sounded more like /{ipa(m.realized)}/."
               if m.kind == "substitution" else f"The /{ipa(m.expected)}/ sound {where} may be missing.")
        issues.append(Issue(
            id=f"ph{m.index}-{m.kind}", type=m.kind, severity=severity, phoneme=ipa(m.expected), position=m.index,
            realized_as=ipa(m.realized), message=msg, evidence=evidence))
    reported = 0
    for p in sorted(parts, key=lambda p: p.similarity):
        if p.status == "good" or reported >= sc.max_parts_reported:
            continue
        lead = "sounded least like the example" if reported == 0 else "also differed from the example"
        msg = " ".join([f"{_cap(p.label)} (/{''.join(p.phonemes)}/) {lead}.", *_part_reasons(p)])
        severity = "minor" if p.status == "fair" else "major" if p.similarity < cfg.rating.strong_error_below \
            else "moderate"
        issues.append(Issue(
            id=f"part{p.index}-mismatch", type="part_mismatch", severity=severity, message=msg,
            evidence={"part": p.index, "label": p.label, "phonemes": p.phonemes, "similarity": p.similarity,
                      "relative_duration": p.relative_duration, "loudness_diff_db": p.loudness_diff_db,
                      "high_band_diff_db": p.high_band_diff_db}))
        reported += 1

    rate = timing.rate_ratio if timing else None
    if syllables and syllables.expected >= 2 and syllables.detected_nuclei is not None:
        found, expected = syllables.detected_nuclei, syllables.expected
        poor_part = any(p.status == "poor" for p in parts)
        if found < expected and poor_part and (rate is None or rate < 0.85):
            issues.append(Issue(
                id="syllables-missing", type="syllable_missing", severity="moderate",
                message=f"{expected - found} of the {expected} syllables may be missing: the recording had "
                        "fewer loudness peaks than the example and was shorter.",
                evidence={"expected": expected, "loudness_peaks": found, "rate_ratio": rate}))
        elif found > expected and poor_part and (rate is None or rate > 1.2):
            issues.append(Issue(
                id="syllables-extra", type="extra_syllable", severity="minor",
                message="There may be an extra syllable: the recording had more loudness peaks than the example.",
                evidence={"expected": expected, "loudness_peaks": found, "rate_ratio": rate}))
    if rate is not None and rate < 0.6:
        issues.append(Issue(id="timing-fast", type="too_fast", severity="minor",
                            message="You said the word faster than the example. Slowing down a little can make "
                                    "each part clearer.", evidence={"rate_ratio": rate}))
    elif rate is not None and rate > 2.2:
        issues.append(Issue(id="timing-slow", type="too_slow", severity="minor",
                            message="You said the word much more slowly than the example. Once it feels "
                                    "comfortable, try a more natural pace.", evidence={"rate_ratio": rate}))

    if n_syl >= 2 and len(comp.parts) >= 2:
        s = comp.standard.features
        user_db = [float(np.mean(user.energy_db[pr.user_start:max(pr.user_end, pr.user_start + 1)]))
                   for pr in comp.parts]
        std_db = [float(np.mean(s.energy_db[pr.part.start:pr.part.end])) for pr in comp.parts]
        u, k = int(np.argmax(user_db)), int(np.argmax(std_db))
        if u != k and user_db[u] - user_db[k] >= 2.0 and std_db[k] - std_db[u] >= 2.0 and k < len(ORDINALS) \
                and u < len(ORDINALS):
            issues.append(Issue(
                id="stress", type="stress_pattern", severity="minor",
                message=f"In the example the {ORDINALS[k]} syllable is the loudest (stressed); in your "
                        f"recording the {ORDINALS[u]} syllable was loudest.",
                evidence={"user_loudest": u, "standard_loudest": k}))
    if pitch is not None and pitch < 40:
        issues.append(Issue(id="pitch", type="pitch_pattern", severity="minor",
                            message="The pitch (melody) moved differently from the example.",
                            evidence={"rms_semitones": comp.pitch_rms_st}))
    if spectral < 45:
        issues.append(Issue(id="overall-different", type="low_acoustic_similarity",
                            severity="major" if spectral < 30 else "moderate",
                            message="Overall, the recording sounded quite different from the example.",
                            evidence={"spectral_similarity": round(spectral, 1)}))

    strengths = [Strength(id=f"part{p.index}-good", message=f"{_cap(p.label)} (/{''.join(p.phonemes)}/) "
                                                            "closely matched the example.")
                 for p in sorted((p for p in parts if p.status == "good"), key=lambda p: -p.similarity)[:2]]
    if loud is not None and loud >= 85 and n_syl >= 2:
        strengths.append(Strength(id="rhythm", message="The rhythm and stress matched the example well."))
    if checks and p_max is not None and p_max < 0.2:
        strengths.append(Strength(id="no-common-mistakes", message="It sounded closer to the correct "
                                  "pronunciation than to the common mistakes we checked."))

    def describe(m) -> str:
        where = describe_position(arpa, m.index)
        if m.kind == "substitution":
            return f"/{ipa(m.realized)}/ instead of /{ipa(m.expected)}/ {where}"
        return f"/{ipa(m.expected)}/ left out {where}"

    signal = SignalAnalysis(
        standard=comp.standard.label, standard_variant=comp.standard.variant_id,
        standards_compared=standards_compared, warp_factor=comp.warp, parts=parts,
        mistakes_checked=[MistakeCheck(description=describe(m), kind=m.kind, phoneme=ipa(m.expected),
                                       realized_as=ipa(m.realized), position=m.index, probability=round(pr, 3))
                          for m, c, pr in checks],
        closest_words=[WordMatch(word=wd, similarity=int(round(distance_score(d, cal.distance_midpoint,
                                                                             cal.distance_scale))))
                       for wd, d in (ident.ranked if ident else [])],
        target_rank=ident.target_rank if ident else None, words_compared=ident.words_compared if ident else 0,
        curves=_curves(user, comp))
    return AnalysisResult(
        **base, status="assessed", needs_retry=False, overall_score=overall, rating=rating,
        phonetically_accurate=None, phoneme_scores=None, signal_analysis=signal,
        identified_issues=issues, strengths=strengths)
