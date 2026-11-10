"""Data contracts for AI feedback (input built from analysis results, output shown to users)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PreviousAttempt(BaseModel):
    overall_score: int | None
    created_at: str | None = None
    phoneme_scores: dict[str, int] = Field(default_factory=dict, description="phoneme -> score for this word")


class FeedbackRequest(BaseModel):
    """What the feedback engine receives.  ``analysis`` is an AnalysisResult dict."""

    analysis: dict
    word: dict | None = Field(None, description="Word database entry (for target sounds / features).")
    previous_attempts: list[PreviousAttempt] = Field(default_factory=list)
    audience: Literal["child", "adult"] = "adult"


class Recommendation(BaseModel):
    issue_id: str = Field(description="ID of the measured issue this tip addresses, or 'general'.")
    tip: str
    articulation: str = Field("", description="Tongue / lip / jaw guidance, empty if not applicable.")


class FeedbackResponse(BaseModel):
    summary: str
    recommendations: list[Recommendation] = Field(default_factory=list)
    encouragement: str = ""
    progress_note: str = ""
    source: str = Field(description="'llm:<provider>:<model>' or 'rule_based'")
    grounded: bool = Field(True, description="All recommendations cite issues measured by the analysis.")
    guardrail_notes: list[str] = Field(default_factory=list, description="What validation removed or changed.")
    disclaimer: str = (
        "This feedback is generated automatically for practice. It is not a diagnosis or a clinical assessment."
    )


# JSON schema the LLM must follow (structured output).  Kept hand-written so it
# stays within the JSON-schema subset supported by structured-output APIs.
LLM_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue_id": {"type": "string"},
                    "tip": {"type": "string"},
                    "articulation": {"type": "string"},
                },
                "required": ["issue_id", "tip", "articulation"],
                "additionalProperties": False,
            },
        },
        "encouragement": {"type": "string"},
        "progress_note": {"type": "string"},
    },
    "required": ["summary", "recommendations", "encouragement", "progress_note"],
    "additionalProperties": False,
}
