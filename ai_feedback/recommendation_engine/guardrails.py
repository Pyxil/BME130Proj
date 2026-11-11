"""Grounding guardrails for LLM output.

The LLM must never invent articulation errors the analysis did not detect.
We enforce this structurally rather than trusting the prompt alone:

1. Every recommendation must cite an ``issue_id`` that exists in the analysis
   (or ``general`` when there are no issues).  Uncited tips are dropped.
2. Every IPA symbol mentioned between slashes must belong to the word, to a
   flagged issue, or to an issue's "sounded like" phone.
3. Diagnostic / clinical language is not allowed.
4. Progress statements must agree with the measured score change.
"""

from __future__ import annotations

import re

from ..contracts import FeedbackRequest, FeedbackResponse, Recommendation
from ..knowledge import normalise_ipa

_SLASHED = re.compile(r"/([^/\s]{1,4})/")
_DIAGNOSTIC = re.compile(
    r"\b(disorder|apraxia|dysarthria|aphasia|lisp(ing)?|stutter(ing)?|diagnos\w*|impairment|"
    r"pathology|delay(ed)? speech|speech delay|therap(y|ist) (is )?(needed|required)|clinical(ly)?)\b",
    re.IGNORECASE,
)
_IMPROVED = re.compile(r"\b(improv\w*|better|progress\w*)\b", re.IGNORECASE)
MAX_LEN = 320


def allowed_symbols(req: FeedbackRequest) -> set[str]:
    a = req.analysis
    syms: set[str] = set()
    for p in a.get("phoneme_scores") or []:
        syms.add(p["phoneme"])
        if p.get("likely_realization"):
            syms.add(p["likely_realization"])
    for i in a.get("identified_issues") or []:
        for k in ("phoneme", "realized_as"):
            if i.get(k):
                syms.add(i[k])
    sig = a.get("signal_analysis") or {}
    for part in sig.get("parts") or []:  # part labels such as /ræ/
        syms.add("".join(part.get("phonemes") or []))
        syms.update(part.get("phonemes") or [])
    for m in sig.get("mistakes_checked") or []:
        for k in ("phoneme", "realized_as"):
            if m.get(k):
                syms.add(m[k])
    mv = a.get("matched_variant") or {}
    for ch in (mv.get("ipa") or "").strip("/"):
        syms.add(ch)
    if req.word:
        syms.update(req.word.get("phonemes") or [])
    return {normalise_ipa(s) for s in syms if s}


def validate(req: FeedbackRequest, out: FeedbackResponse) -> tuple[FeedbackResponse, list[str]]:
    notes: list[str] = []
    issues = {i["id"]: i for i in req.analysis.get("identified_issues") or []}
    allowed = allowed_symbols(req)

    def bad_symbols(text: str) -> list[str]:
        return [s for s in _SLASHED.findall(text) if normalise_ipa(s) not in allowed]

    kept: list[Recommendation] = []
    for r in out.recommendations:
        text = f"{r.tip} {r.articulation}"
        if r.issue_id not in issues and not (r.issue_id == "general" and not issues):
            notes.append(f"dropped recommendation citing unknown issue '{r.issue_id}'")
            continue
        bad = bad_symbols(text)
        if bad:
            notes.append(f"dropped recommendation mentioning sounds not measured: {bad}")
            continue
        if _DIAGNOSTIC.search(text):
            notes.append("dropped recommendation containing diagnostic language")
            continue
        kept.append(Recommendation(issue_id=r.issue_id, tip=r.tip[:MAX_LEN], articulation=r.articulation[:MAX_LEN]))
    out.recommendations = kept[:3]

    for field in ("summary", "encouragement", "progress_note"):
        text = getattr(out, field)
        if _DIAGNOSTIC.search(text) or bad_symbols(text):
            notes.append(f"removed {field}: unsupported sound or diagnostic language")
            setattr(out, field, "")
        else:
            setattr(out, field, text[:MAX_LEN])

    # progress must match the measured change
    prev = [p.overall_score for p in req.previous_attempts if p.overall_score is not None]
    score = req.analysis.get("overall_score")
    if not prev and out.progress_note:
        notes.append("removed progress note: no previous attempts")
        out.progress_note = ""
    elif prev and score is not None and out.progress_note:
        if score - prev[-1] < 0 and _IMPROVED.search(out.progress_note) and "lower" not in out.progress_note.lower():
            notes.append("removed progress note claiming improvement when the score dropped")
            out.progress_note = ""
    out.grounded = True
    return out, notes
