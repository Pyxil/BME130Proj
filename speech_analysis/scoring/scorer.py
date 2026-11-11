"""Combine evidence into the final :class:`AnalysisResult`.

Every number in the result is computed from the recording: phoneme scores
come from the engine's GOP posteriors (calibrated against human ratings),
issues are only raised from measured evidence, and nothing is randomised.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..calibration import PhoneCalibration
from ..config import AnalysisConfig
from ..contracts import (
    AnalysisResult,
    ComponentScore,
    EngineInfo,
    Issue,
    MatchedVariant,
    PhonemeScore,
    QualityReport,
    Strength,
    SyllableReport,
    TimingReport,
    WordRecognition,
)
from ..phoneme_analysis.engines.base import EngineOutput, VariantAssessment
from ..phoneme_analysis.phonemes import ipa_for, is_vowel, syllabify
from .acoustic_similarity import SimilarityResult
from .components import syllable_completeness

ORDINAL = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh"]
_LABEL_IPA = {"AH": "ʌ", "AH0": "ə", "ER": "ɜr"}


def label_ipa(label: str | None) -> str | None:
    if label is None:
        return None
    return _LABEL_IPA.get(label) or ipa_for(label + ("1" if label in {
        "AA", "AE", "AO", "AW", "AY", "EH", "EY", "IH", "IY", "OW", "OY", "UH", "UW"} else ""))


def describe_position(arpabet: list[str], index: int) -> str:
    """Human-readable location of a phone: 'at the start', 'in the second syllable', ..."""
    sylls = syllabify(arpabet)
    k, syl_idx = 0, 0
    for s_i, syl in enumerate(sylls):
        if index < k + len(syl):
            syl_idx = s_i
            break
        k += len(syl)
    if index == 0:
        return "at the start of the word"
    if index == len(arpabet) - 1:
        return "at the end of the word"
    if len(sylls) == 1:
        return "in the middle of the word"
    return f"in the {ORDINAL[min(syl_idx, len(ORDINAL) - 1)]} syllable"


@dataclass
class Evidence:
    word: dict
    quality: QualityReport
    engine: EngineOutput | None
    engine_info: EngineInfo
    similarity: SimilarityResult | None
    syllables: SyllableReport | None
    timing: TimingReport | None
    temporal_score: float | None


def _phone_scores(variant: VariantAssessment, cal: PhoneCalibration | None,
                  cfg: AnalysisConfig) -> list[PhonemeScore]:
    out = []
    t = cfg.phoneme
    for p in variant.phones:
        score = cal.score(p.posterior, p.arpabet) if cal else int(round(100 * p.posterior))
        missing = p.best_alternative is None and p.deletion_prob >= t.report_deletion_min_prob
        if missing and score < t.fair:
            status = "missing"
        elif score >= t.good:
            status = "good"
        elif score >= t.fair:
            status = "fair"
        else:
            status = "poor"
        likely = None
        likely_p = None
        if status in {"poor", "fair"} and p.best_alternative is not None \
                and p.best_alternative_prob >= t.report_substitution_min_prob:
            likely, likely_p = label_ipa(p.best_alternative), round(p.best_alternative_prob, 3)
        out.append(PhonemeScore(
            index=p.index, phoneme=ipa_for(p.arpabet), arpabet=p.arpabet, score=score,
            posterior=round(min(1.0, max(0.0, p.posterior)), 4), status=status,
            likely_realization=likely, likely_realization_probability=likely_p,
            deletion_probability=round(p.deletion_prob, 3),
            accepted_variant=label_ipa(p.accepted_variant), start_s=p.start_s, end_s=p.end_s,
        ))
    return out


def _issues_and_strengths(word: dict, arpabet: list[str], scores: list[PhonemeScore] | None,
                          ev: Evidence, cfg: AnalysisConfig) -> tuple[list[Issue], list[Strength]]:
    issues: list[Issue] = []
    strengths: list[Strength] = []
    if scores:
        ranked = sorted(scores, key=lambda s: s.score if s.score is not None else 100)
        for s in ranked:
            if s.status not in {"poor", "missing", "fair"}:
                continue
            where = describe_position(arpabet, s.index)
            kind = "vowel" if is_vowel(s.arpabet) else "sound"
            sev = "major" if (s.score or 0) < 30 else "moderate" if (s.score or 0) < cfg.phoneme.fair else "minor"
            evidence = {"score": s.score, "posterior": s.posterior, "deletion_probability": s.deletion_probability}
            if s.status == "missing":
                issues.append(Issue(
                    id=f"ph{s.index}-deletion", type="deletion", severity=sev, phoneme=s.phoneme, position=s.index,
                    message=f"The /{s.phoneme}/ {kind} {where} may be missing.", evidence=evidence))
            elif s.likely_realization:
                evidence["likely_realization_probability"] = s.likely_realization_probability
                issues.append(Issue(
                    id=f"ph{s.index}-substitution", type="substitution", severity=sev, phoneme=s.phoneme,
                    position=s.index, realized_as=s.likely_realization,
                    message=f"The /{s.phoneme}/ {kind} {where} may have sounded more like /{s.likely_realization}/.",
                    evidence=evidence))
            elif s.status in {"poor", "fair"}:
                adj = "was not clearly identified" if s.status == "poor" else "could be clearer"
                issues.append(Issue(
                    id=f"ph{s.index}-unclear", type="unclear_articulation", severity=sev, phoneme=s.phoneme,
                    position=s.index, message=f"The /{s.phoneme}/ {kind} {where} {adj}.", evidence=evidence))
        target = set(word.get("target_sounds") or [])
        good = [s for s in scores if s.status == "good" and (s.score or 0) >= 85]
        good.sort(key=lambda s: (s.phoneme not in target, -(s.score or 0)))
        for s in good[:3]:
            where = describe_position(arpabet, s.index)
            strengths.append(Strength(id=f"ph{s.index}-good", phoneme=s.phoneme, position=s.index,
                                      message=f"The /{s.phoneme}/ {where} was clear."))
        # feature-level strengths (e.g. clusters) when every phone in the feature is good
        for f in word.get("evaluation_features", []):
            if f["type"] in {"initial_cluster", "final_cluster", "medial_cluster"} and f["positions"] \
                    and len(arpabet) == len(word.get("arpabet", [])):
                if all(scores[i].status == "good" for i in f["positions"] if i < len(scores)):
                    strengths.append(Strength(id=f"feat-{f['type']}-{f['positions'][0]}",
                                              message=f"{f['description']} was produced clearly."))
    syl = ev.syllables
    # Report a missing syllable only when two independent signals agree: the model finds a vowel
    # missing AND the acoustic nucleus count is short (either alone produces false alarms).
    acoustic_short = syl is None or syl.detected_nuclei is None or syl.detected_nuclei < syl.expected
    if syl and syl.vowels_present is not None and syl.vowels_present < syl.expected and acoustic_short:
        missing = syl.expected - syl.vowels_present
        issues.append(Issue(
            id="syllable-missing", type="syllable_missing", severity="moderate",
            message=f"{missing} of the {syl.expected} syllables may be missing or very reduced.",
            evidence={"expected": syl.expected, "vowels_present": syl.vowels_present,
                      "detected_nuclei": syl.detected_nuclei}))
    if syl and syl.detected_nuclei is not None:
        extra_needed = 1 if syl.expected <= 2 else 2
        if syl.detected_nuclei >= syl.expected + extra_needed:
            issues.append(Issue(
                id="syllable-extra", type="extra_syllable", severity="minor",
                message="An extra syllable may have been added (for example a vowel between consonants).",
                evidence={"expected": syl.expected, "detected_nuclei": syl.detected_nuclei}))
    if ev.timing and ev.timing.rate_ratio is not None:
        if ev.timing.rate_ratio < 0.6:
            issues.append(Issue(id="timing-fast", type="too_fast", severity="minor",
                                message="The word was said much faster than the example. Try slowing down.",
                                evidence={"rate_ratio": ev.timing.rate_ratio}))
        elif ev.timing.rate_ratio > 2.6:
            issues.append(Issue(id="timing-slow", type="too_slow", severity="minor",
                                message="The word was stretched out a lot. Once it feels easy, try a natural pace.",
                                evidence={"rate_ratio": ev.timing.rate_ratio}))
    if ev.similarity is not None and ev.similarity.similarity < 0.3:
        issues.append(Issue(id="acoustic-low", type="low_acoustic_similarity", severity="minor",
                            message="The overall sound pattern differed noticeably from the example recording.",
                            evidence={"similarity": ev.similarity.similarity}))
    sev_rank = {"major": 0, "moderate": 1, "minor": 2}
    issues.sort(key=lambda i: sev_rank[i.severity])
    return issues[:5], strengths[:4]


def _confidence(ev: Evidence, phone_accuracy: float | None, cfg: AnalysisConfig) -> dict[str, float]:
    q = ev.quality
    f: dict[str, float] = {}
    snr = q.snr_db if q.snr_db is not None else cfg.quality.warn_snr_db
    lo, hi = cfg.quality.min_snr_db, cfg.quality.warn_snr_db
    f["recording_quality"] = float(np.clip(0.5 + 0.5 * (snr - lo) / max(1e-6, hi - lo), 0.5, 1.0))
    if any(not i.blocking for i in q.issues):
        f["recording_quality"] *= 0.9
    if ev.engine is None:
        f["phoneme_model"] = 0.55  # acoustic-only baseline: no phoneme-level evidence
    else:
        f["phoneme_model"] = 1.0
        # agreement between word recognition and phoneme scores
        rec = ev.engine.recognized_matches_target
        if rec is False and phone_accuracy is not None and phone_accuracy >= cfg.rating.satisfactory:
            f["consistency"] = 0.6  # phones look fine but another word explains the audio better
        elif rec is False and phone_accuracy is not None and phone_accuracy < 40:
            f["consistency"] = 0.85  # consistently poor: low score is credible
        elif rec is False:
            f["consistency"] = 0.75
        else:
            f["consistency"] = 1.0
    if ev.timing and ev.timing.rate_ratio is not None:
        r = ev.timing.rate_ratio
        f["duration_plausibility"] = 1.0 if 0.4 <= r <= 3.5 else 0.6 if 0.25 <= r <= 5.0 else 0.35
    return {k: round(v, 3) for k, v in f.items()}


def build_result(ev: Evidence, cfg: AnalysisConfig, cal: PhoneCalibration | None, analysis_id: str,
                 processing_ms: int) -> AnalysisResult:
    word = ev.word
    base = dict(analysis_id=analysis_id, word=word["word"], word_id=word.get("id"), quality=ev.quality,
                engine=ev.engine_info, processing_ms=processing_ms)
    if not ev.quality.usable:
        reasons = [i.message for i in ev.quality.issues if i.blocking]
        return AnalysisResult(**base, status="retry_required", confidence=0.0, confidence_label="low",
                              needs_retry=True, retry_reason=" ".join(reasons[:2]) or "Please record again.")

    variant = ev.engine.best if ev.engine else None
    arpabet = variant.arpabet if variant else word["arpabet"]
    matched = None
    if variant:
        vmeta = next((v for v in word["variants"] if v["id"] == variant.variant_id), word["variants"][0])
        matched = MatchedVariant(id=vmeta["id"], accent=vmeta["accent"], ipa=vmeta["ipa"], arpabet=vmeta["arpabet"])
    scores = _phone_scores(variant, cal, cfg) if variant else None
    if scores and variant is not None and ev.syllables is not None:
        # A vowel counts as absent when deleting it is the model's best explanation AND its
        # calibrated status is not "good" (keeps syllable evidence consistent with the sound chips).
        flags = [not (vp.best_alternative is None and vp.deletion_prob >= cfg.phoneme.report_deletion_min_prob
                      and s.status != "good")
                 for vp, s in zip(variant.phones, scores) if is_vowel(s.arpabet)]
        ev.syllables = syllable_completeness(ev.syllables.expected, ev.syllables.detected_nuclei, vowel_present=flags)

    phone_acc = None
    aggregation = None
    if scores:
        vals = [float(s.score) for s in scores]
        word_cal = cal.word_score(vals) if cal else None
        if word_cal is not None:
            # expected expert word rating, fitted on speechocean762 word scores
            phone_acc, aggregation = word_cal, "word-level calibration of calibrated phone scores"
        else:
            # soft-min: one badly produced sound matters more than the plain mean suggests
            arr = np.array(vals)
            phone_acc, aggregation = float(0.6 * arr.mean() + 0.4 * arr.min()), "0.6*mean + 0.4*min"

    w = cfg.weights
    comps = [
        ComponentScore(name="phoneme_accuracy", score=None if phone_acc is None else round(phone_acc, 1),
                       weight=w.phoneme_accuracy, available=phone_acc is not None,
                       details={"aggregation": aggregation, "calibration": cal.source if cal else None}),
        ComponentScore(name="acoustic_similarity",
                       score=None if ev.similarity is None else round(100 * ev.similarity.similarity, 1),
                       weight=w.acoustic_similarity, available=ev.similarity is not None,
                       details={} if ev.similarity is None else {
                           "dtw_cost": ev.similarity.best_cost, "reference": ev.similarity.best_reference,
                           "warp": ev.similarity.warp, "references_compared": len(ev.similarity.per_reference)}),
        ComponentScore(name="syllable_completeness",
                       score=None if not ev.syllables or ev.syllables.completeness is None
                       else round(100 * ev.syllables.completeness, 1),
                       weight=w.syllable_completeness,
                       available=bool(ev.syllables and ev.syllables.completeness is not None),
                       details={} if not ev.syllables else ev.syllables.model_dump()),
        ComponentScore(name="temporal", score=ev.temporal_score, weight=w.temporal,
                       available=ev.temporal_score is not None,
                       details={} if not ev.timing else ev.timing.model_dump()),
    ]
    avail = [c for c in comps if c.available and c.score is not None]
    total_w = sum(c.weight for c in avail)
    overall = round(sum(c.score * c.weight for c in avail) / total_w) if total_w > 0 else None

    factors = _confidence(ev, phone_acc, cfg)
    confidence = float(np.prod(list(factors.values()))) if factors else 0.5
    ct = cfg.confidence
    label = "high" if confidence >= ct.high_at_or_above else "medium" if confidence >= ct.low_below else "low"

    recognition = None
    if ev.engine:
        recognition = WordRecognition(
            recognized_phonemes=ev.engine.decoded_ipa, closest_word=ev.engine.recognized_word,
            matches_target=ev.engine.recognized_matches_target, phoneme_error_rate=ev.engine.phoneme_error_rate)

    issues, strengths = _issues_and_strengths(word, arpabet, scores, ev, cfg)
    common = dict(
        **base, confidence=round(confidence, 3), confidence_label=label, confidence_factors=factors,
        matched_variant=matched, components=comps,
        acoustic_similarity=None if ev.similarity is None else ev.similarity.similarity,
        syllables=ev.syllables, timing=ev.timing, recognition=recognition,
        word_recognized=None if ev.engine is None else ev.engine.recognized_matches_target,
        recognized_word=None if ev.engine is None else ev.engine.recognized_word,
    )
    if overall is None or confidence < ct.inconclusive_below:
        return AnalysisResult(
            **common, status="inconclusive", needs_retry=True, overall_score=None, phoneme_scores=None,
            identified_issues=[], strengths=[],
            retry_reason="We couldn't analyse this recording reliably. Please say the word once more, clearly, "
                         "in a quiet place.")
    all_good = scores is None or all(s.status == "good" for s in scores)
    strong_error = bool(scores) and any(s.status in {"poor", "missing"} and (s.score or 0) < cfg.rating.strong_error_below
                                        for s in scores)
    # Consistency rules (configurable): the number must agree with the label.
    cap = None
    if cfg.rating.cap_scores and scores:
        if strong_error and overall >= cfg.rating.satisfactory:
            overall, cap = cfg.rating.satisfactory - 1, "a sound scored below the strong-error threshold"
        elif not all_good and overall >= cfg.rating.mastered:
            overall, cap = cfg.rating.mastered - 1, "not every sound was rated good"
    if cap:
        comps[0].details["score_cap"] = cap
    if overall >= cfg.rating.mastered and all_good:
        rating = "mastered"
    elif overall < cfg.rating.satisfactory or strong_error:
        rating = "needs_practice"
    else:
        rating = "satisfactory"
    accurate = None if scores is None else bool(all_good and overall >= cfg.rating.mastered)
    return AnalysisResult(
        **common, status="assessed", needs_retry=False, overall_score=int(overall), rating=rating,
        phonetically_accurate=accurate, phoneme_scores=scores, identified_issues=issues, strengths=strengths)
