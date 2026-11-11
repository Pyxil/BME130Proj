"""Deterministic, rule-based feedback.

Used when no LLM is configured, when the LLM fails, or when its output does
not pass the grounding guardrails.  Every sentence is derived from the
analysis result and the curated articulation knowledge base.
"""

from __future__ import annotations

from ..contracts import FeedbackRequest, FeedbackResponse, Recommendation
from ..knowledge import contrast_note, pattern_note, phoneme_note


def progress_note(req: FeedbackRequest) -> str:
    """Compare with earlier attempts using measured scores only."""
    score = req.analysis.get("overall_score")
    prev = [p.overall_score for p in req.previous_attempts if p.overall_score is not None]
    if score is None or not prev:
        return ""
    last, best = prev[-1], max(prev)
    delta = score - last
    if delta >= 5:
        note = f"Your score improved by {delta} points compared with your last attempt ({last} -> {score})."
    elif delta <= -5:
        note = f"This attempt scored {abs(delta)} points lower than your last one ({last} -> {score}). That's normal when practising; take a breath and try again."
    else:
        note = f"Your score is similar to your last attempt ({last} -> {score})."
    if score > best and len(prev) > 1:
        note += " This is your best score on this word so far."
    return note


def _tip_for(issue: dict, word: str, n_phones: int) -> Recommendation:
    t = issue["type"]
    ph = issue.get("phoneme")
    real = issue.get("realized_as")
    note = phoneme_note(ph)
    label = note["label"] if note else (f"/{ph}/" if ph else "")
    how = note["how"] if note else ""
    pos = issue.get("position")
    if t == "substitution":
        contrast = contrast_note(ph, real)
        tip = f"Focus on the /{ph}/ sound ({label}). It may have sounded more like /{real}/."
        return Recommendation(issue_id=issue["id"], tip=tip, articulation=contrast or how)
    if t == "deletion":
        if pos == 0:
            key = "deletion_initial"
        elif pos is not None and pos >= n_phones - 1:
            key = "deletion_final"
        else:
            key = "deletion_cluster"
        tip = f"The /{ph}/ sound ({label}) may be missing. {pattern_note(key) or ''}".strip()
        return Recommendation(issue_id=issue["id"], tip=tip, articulation=how)
    if t == "unclear_articulation":
        tip = f"Try to make the /{ph}/ sound ({label}) a little clearer."
        if note is None:
            tip += " " + (pattern_note("unclear_vowel") or "")
        return Recommendation(issue_id=issue["id"], tip=tip.strip(), articulation=how)
    if t == "part_mismatch":
        return Recommendation(issue_id=issue["id"], tip=issue["message"], articulation=pattern_note("part_mismatch"))
    if t in ("stress_pattern", "pitch_pattern"):
        return Recommendation(issue_id=issue["id"], tip=issue["message"], articulation=pattern_note(t))
    key = {"syllable_missing": "syllable_missing", "extra_syllable": "extra_syllable", "too_fast": "too_fast",
           "too_slow": "too_slow", "low_acoustic_similarity": "low_acoustic_similarity"}.get(t)
    return Recommendation(issue_id=issue["id"], tip=pattern_note(key) if key else issue["message"], articulation="")


def rule_based_feedback(req: FeedbackRequest, reason: str | None = None) -> FeedbackResponse:
    a = req.analysis
    word = a.get("word", "")
    status = a.get("status")
    notes = [reason] if reason else []
    if status != "assessed":
        return FeedbackResponse(
            summary=a.get("retry_reason") or "Please record the word again.",
            recommendations=[], encouragement="Take your time, then press Record when you are ready.",
            progress_note="", source="rule_based", guardrail_notes=notes)
    score = a.get("overall_score")
    rating = a.get("rating")
    issues = a.get("identified_issues") or []
    strengths = a.get("strengths") or []
    n_phones = len(a.get("phoneme_scores") or []) or 1
    if rating == "mastered":
        summary = f"Excellent - '{word}' sounded clear ({score}/100)."
    elif rating == "satisfactory":
        summary = f"Good attempt at '{word}' ({score}/100). A little practice will make it even clearer."
    else:
        summary = f"'{word}' scored {score}/100. Let's practise it with the tips below."
    if strengths:
        summary += " " + strengths[0]["message"]
    recs = [_tip_for(i, word, n_phones) for i in issues[:3]]
    if a.get("confidence_label") == "low":
        summary += " (The analysis was less certain for this recording.)"
    encouragement = "Listen to the example once more, then try again slowly." if recs else \
        "Great work! Try the next word when you're ready."
    return FeedbackResponse(summary=summary, recommendations=recs, encouragement=encouragement,
                            progress_note=progress_note(req), source="rule_based", guardrail_notes=notes)
