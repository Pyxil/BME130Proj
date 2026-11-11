"""Typed request/response models for the REST API (exported to OpenAPI and TypeScript)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_feedback.contracts import FeedbackResponse
from speech_analysis.contracts import AnalysisResult

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SessionMode = Literal["adaptive", "random", "easy", "medium", "hard", "phoneme", "missed"]


class ErrorResponse(BaseModel):
    detail: str


# Explicit descriptions keep docs/openapi.json identical on every Python version: 3.13 renamed the
# standard phrases for 413 and 422, which FastAPI would otherwise copy into the schema.
UNPROCESSABLE = {"model": ErrorResponse, "description": "Unprocessable Content"}
TOO_LARGE = {"model": ErrorResponse, "description": "Content Too Large"}


# ---------------------------------------------------------------- auth / users
class RegisterRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field("", max_length=100)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("invalid email address")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    display_name: str
    audience: Literal["adult", "child"]
    preferred_accent: Literal["us", "gb"]
    store_recordings_consent: bool
    created_at: datetime


class UserUpdate(BaseModel):
    display_name: str | None = Field(None, max_length=100)
    audience: Literal["adult", "child"] | None = None
    preferred_accent: Literal["us", "gb"] | None = None
    store_recordings_consent: bool | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut


# ----------------------------------------------------------------------- words
class WordVariantOut(BaseModel):
    id: str
    accent: str
    ipa: str
    arpabet: list[str]


class EvaluationFeature(BaseModel):
    type: str
    positions: list[int]
    phonemes: list[str]
    description: str
    value: int | None = None


class WordSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    word: str
    ipa: str
    phonemes: list[str]
    syllables: int
    difficulty: Literal["easy", "medium", "hard"]
    category: str
    category_label: str
    target_sounds: list[str]


class WordDetail(WordSummary):
    arpabet: list[str]
    variants: list[WordVariantOut]
    evaluation_features: list[EvaluationFeature]
    stress_pattern: list[int]
    syllable_breakdown: list[list[str]]
    notes: str | None = None


class WordList(BaseModel):
    total: int
    items: list[WordSummary]


class PhonemeOption(BaseModel):
    phoneme: str
    label: str
    kind: Literal["vowel", "consonant"]
    word_count: int


# -------------------------------------------------------------------- sessions
class SessionCreate(BaseModel):
    mode: SessionMode = "adaptive"
    phoneme: str | None = Field(None, max_length=8, description="IPA symbol for mode='phoneme'")
    size: int = Field(10, ge=3, le=30)


class SessionWordProgress(BaseModel):
    position: int
    word: WordSummary
    attempts: int
    best_score: int | None
    last_score: int | None
    last_rating: str | None
    status: Literal["pending", "attempted", "mastered"]


class SessionOut(BaseModel):
    id: str
    mode: SessionMode
    target_phoneme: str | None
    status: Literal["active", "completed"]
    started_at: datetime
    completed_at: datetime | None
    current_index: int
    total_words: int
    words_attempted: int
    average_score: float | None
    words: list[SessionWordProgress]
    focus_phonemes: list[str] = Field(default_factory=list, description="Sounds the adaptive planner is prioritising.")


class SessionAdvance(BaseModel):
    current_index: int | None = Field(None, ge=0, description="Jump to an index; omit to move to the next word.")


class SessionSummary(BaseModel):
    id: str
    mode: SessionMode
    status: str
    started_at: datetime
    completed_at: datetime | None
    total_words: int
    words_attempted: int
    attempts: int
    average_score: float | None


# -------------------------------------------------------------------- attempts
class AttemptOut(BaseModel):
    attempt_id: str
    attempt_number: int
    word_id: int
    session_id: str | None
    created_at: datetime
    analysis: AnalysisResult
    feedback: FeedbackResponse | None = None
    has_recording: bool = False
    word_best_score: int | None = None


class AttemptSummary(BaseModel):
    id: str
    word_id: int
    word: str
    session_id: str | None
    created_at: datetime
    attempt_number: int
    status: str
    overall_score: int | None
    rating: str | None
    confidence: float
    has_recording: bool
    feedback_summary: str | None = None


class AttemptList(BaseModel):
    total: int
    items: list[AttemptSummary]


class FeedbackRequestIn(BaseModel):
    attempt_id: str | None = Field(None, description="Generate (and store) feedback for a saved attempt.")
    analysis: AnalysisResult | None = Field(None, description="Or pass an analysis result directly (stateless).")


# -------------------------------------------------------------------- progress
class ScorePoint(BaseModel):
    date: str
    average_score: float
    attempts: int


class PhonemeStat(BaseModel):
    phoneme: str
    attempts: int
    average_score: float
    poor_count: int
    poor_rate: float
    common_substitution: str | None = None


class WordProgress(BaseModel):
    word_id: int
    word: str
    attempts: int
    best_score: int | None
    last_score: int | None
    last_rating: str | None
    last_attempt_at: datetime


class ProgressOut(BaseModel):
    average_score: float | None
    total_attempts: int
    assessed_attempts: int
    words_attempted: int
    words_completed: int = Field(description="Distinct words with at least one scored attempt.")
    words_mastered: int
    total_sessions: int
    improvement: float | None = Field(None, description="Average of the last 10 scored attempts minus the first 10.")
    score_over_time: list[ScorePoint]
    phoneme_stats: list[PhonemeStat]
    most_mispronounced: list[PhonemeStat]
    words_needing_practice: list[WordProgress]
    recent_sessions: list[SessionSummary]
    recent_attempts: list[AttemptSummary]


class SystemStatus(BaseModel):
    status: Literal["ok"]
    environment: str
    contract_version: str
    analysis_engine: dict
    feedback: dict
    reference_audio: dict
    words: int
