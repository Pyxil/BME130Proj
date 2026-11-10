"""Stable data contracts for pronunciation analysis results.

These Pydantic models are the single source of truth for the analysis JSON
that flows from ``speech_analysis`` -> backend API -> frontend / AI feedback.
JSON Schemas are exported to ``docs/schemas/`` and TypeScript types are
generated from the backend OpenAPI document, so changing a field here is a
contract change: update ``CONTRACT_VERSION`` and the docs.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CONTRACT_VERSION = "1.0.0"

DISCLAIMER = (
    "Scores are automated estimates intended for practice feedback. They are not a clinical "
    "assessment or diagnosis and have not been clinically validated."
)

AssessmentStatus = Literal["assessed", "retry_required", "inconclusive"]
Rating = Literal["mastered", "satisfactory", "needs_practice"]
PhonemeStatus = Literal["good", "fair", "poor", "missing", "unscored"]
IssueType = Literal[
    "substitution",
    "deletion",
    "unclear_articulation",
    "insertion",
    "syllable_missing",
    "extra_syllable",
    "too_fast",
    "too_slow",
    "low_acoustic_similarity",
]
Severity = Literal["minor", "moderate", "major"]


class QualityIssue(BaseModel):
    code: Literal[
        "too_short", "too_long", "no_speech", "too_quiet", "clipping", "noisy",
        "truncated_start", "truncated_end", "decode_error",
    ]
    message: str
    blocking: bool = Field(description="If true the recording is rejected and the user is asked to record again.")


class QualityReport(BaseModel):
    usable: bool
    duration_s: float
    speech_duration_s: float
    speech_start_s: float
    speech_end_s: float
    rms_dbfs: float | None = None
    peak_dbfs: float | None = None
    snr_db: float | None = Field(None, description="Estimated speech-to-background level difference in dB.")
    clipping_ratio: float = 0.0
    issues: list[QualityIssue] = Field(default_factory=list)


class PhonemeScore(BaseModel):
    index: int = Field(description="Position in the expected phoneme sequence of the matched variant.")
    phoneme: str = Field(description="Expected phoneme (broad IPA).")
    arpabet: str = Field(description="Expected phoneme (ARPAbet with stress).")
    score: int | None = Field(None, ge=0, le=100, description="Calibrated 0-100 phoneme score.")
    posterior: float | None = Field(
        None, ge=0, le=1,
        description="Model probability that the expected sound (or an accepted variant of it) was produced.",
    )
    status: PhonemeStatus
    likely_realization: str | None = Field(
        None, description="Most likely competing sound (IPA) when the expected one scored low.",
    )
    likely_realization_probability: float | None = None
    deletion_probability: float | None = None
    accepted_variant: str | None = Field(
        None, description="Accepted allophone/accent realisation that explained the audio better, if any.",
    )
    start_s: float | None = Field(None, description="Approximate start time (seconds, trimmed audio).")
    end_s: float | None = None


class ComponentScore(BaseModel):
    name: Literal["phoneme_accuracy", "acoustic_similarity", "syllable_completeness", "temporal"]
    score: float | None = Field(None, ge=0, le=100)
    weight: float = Field(description="Configured weight (renormalised over available components).")
    available: bool
    details: dict[str, Any] = Field(default_factory=dict)


class Issue(BaseModel):
    id: str = Field(description="Stable identifier within this result; AI feedback must cite these.")
    type: IssueType
    severity: Severity
    phoneme: str | None = None
    position: int | None = None
    realized_as: str | None = None
    message: str = Field(description="Plain-language description generated from measured data.")
    evidence: dict[str, Any] = Field(default_factory=dict)


class Strength(BaseModel):
    id: str
    message: str
    phoneme: str | None = None
    position: int | None = None


class WordRecognition(BaseModel):
    recognized_phonemes: list[str] = Field(default_factory=list, description="Free phone decoding (IPA).")
    closest_word: str | None = Field(None, description="Practice word whose pronunciation best matches the decoding.")
    matches_target: bool | None = None
    phoneme_error_rate: float | None = Field(
        None, description="Edit distance between the free decoding and the matched variant, divided by its length.",
    )


class SyllableReport(BaseModel):
    expected: int
    detected_nuclei: int | None = None
    vowels_present: int | None = None
    completeness: float | None = Field(None, ge=0, le=1)


class TimingReport(BaseModel):
    speech_duration_s: float
    reference_duration_s: float | None = None
    rate_ratio: float | None = Field(None, description="User duration / reference duration.")
    rhythm_deviation: float | None = Field(None, description="Mean |log| ratio of relative phone durations.")


class MatchedVariant(BaseModel):
    id: str
    accent: str
    ipa: str
    arpabet: list[str]


class EngineInfo(BaseModel):
    name: str
    model: str | None = None
    phoneme_level: bool = Field(description="True if the engine produced genuine phoneme-level scores.")
    calibration: str | None = None
    notes: str | None = None


class AnalysisResult(BaseModel):
    contract_version: str = CONTRACT_VERSION
    analysis_id: str
    word: str
    word_id: int | None = None
    status: AssessmentStatus
    overall_score: int | None = Field(None, ge=0, le=100)
    rating: Rating | None = None
    word_recognized: bool | None = Field(
        None, description="Whether the decoded sounds match the target word better than other practice words.",
    )
    recognized_word: str | None = None
    phonetically_accurate: bool | None = Field(
        None, description="True only if every phoneme scored 'good' and the overall score meets the mastery threshold.",
    )
    confidence: float = Field(ge=0, le=1)
    confidence_label: Literal["high", "medium", "low"]
    confidence_factors: dict[str, float] = Field(default_factory=dict)
    needs_retry: bool
    retry_reason: str | None = None
    matched_variant: MatchedVariant | None = None
    phoneme_scores: list[PhonemeScore] | None = None
    components: list[ComponentScore] = Field(default_factory=list)
    acoustic_similarity: float | None = Field(None, ge=0, le=1)
    syllables: SyllableReport | None = None
    timing: TimingReport | None = None
    recognition: WordRecognition | None = None
    quality: QualityReport
    identified_issues: list[Issue] = Field(default_factory=list)
    strengths: list[Strength] = Field(default_factory=list)
    engine: EngineInfo
    processing_ms: int = 0
    disclaimer: str = DISCLAIMER
