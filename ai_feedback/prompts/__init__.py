"""Prompt templates and the grounded payload sent to the LLM."""

from __future__ import annotations

import json
from pathlib import Path

from ..contracts import FeedbackRequest
from ..knowledge import contrast_note, pattern_note, phoneme_note

SYSTEM_PROMPT = (Path(__file__).resolve().parent / "system_prompt.md").read_text(encoding="utf-8")


def build_payload(req: FeedbackRequest) -> dict:
    """Compact, factual payload: only measured data plus curated articulation notes."""
    a = req.analysis
    issues = a.get("identified_issues") or []
    notes: dict[str, str] = {}
    for i in issues:
        ph, real = i.get("phoneme"), i.get("realized_as")
        n = phoneme_note(ph)
        if n:
            notes[f"/{ph}/"] = f"{n['label']}: {n['how']}"
        c = contrast_note(ph, real)
        if c:
            notes[f"/{ph}/ vs /{real}/"] = c
        p = pattern_note({"syllable_missing": "syllable_missing", "extra_syllable": "extra_syllable",
                          "too_fast": "too_fast", "too_slow": "too_slow"}.get(i["type"], ""))
        if p:
            notes[i["type"]] = p
    return {
        "target_word": a.get("word"),
        "expected_pronunciation": (a.get("matched_variant") or {}).get("ipa"),
        "accent_variant_matched": (a.get("matched_variant") or {}).get("accent"),
        "overall_score": a.get("overall_score"),
        "rating": a.get("rating"),
        "confidence": a.get("confidence_label"),
        "word_recognized": a.get("word_recognized"),
        "recognized_sounds": (a.get("recognition") or {}).get("recognized_phonemes"),
        "phoneme_scores": [
            {"sound": p["phoneme"], "score": p["score"], "status": p["status"],
             "may_have_sounded_like": p.get("likely_realization")}
            for p in a.get("phoneme_scores") or []
        ],
        "acoustic": {
            "similarity_to_example": a.get("acoustic_similarity"),
            "syllables": a.get("syllables"),
            "timing": a.get("timing"),
        },
        "identified_issues": [
            {k: i.get(k) for k in ("id", "type", "severity", "phoneme", "realized_as", "message")} for i in issues
        ],
        "strengths": [s["message"] for s in a.get("strengths") or []],
        "previous_attempts": [p.model_dump() for p in req.previous_attempts[-5:]],
        "audience": req.audience,
        "articulation_notes": notes,
    }


def user_message(req: FeedbackRequest) -> str:
    return (
        "Analysis results for one practice attempt (JSON). Write the feedback object.\n\n"
        + json.dumps(build_payload(req), ensure_ascii=False, indent=1)
    )
