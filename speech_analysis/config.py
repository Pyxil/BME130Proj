"""Configuration for the analysis pipeline.

Every weight and threshold here is an *engineering assumption*, not a
clinically validated value.  Override them with a JSON file
(``SPEECH_ANALYSIS_CONFIG=/path/config.json``) or individual environment
variables prefixed ``SA_`` (for example ``SA_WEIGHT_PHONEME=0.7``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent


class ScoreWeights(BaseModel):
    phoneme_accuracy: float = 0.60
    acoustic_similarity: float = 0.20
    syllable_completeness: float = 0.10
    temporal: float = 0.10


class QualityThresholds(BaseModel):
    min_duration_s: float = 0.25
    max_duration_s: float = 15.0
    min_speech_s: float = 0.15
    min_rms_dbfs: float = -45.0  # speech region level below this = too quiet
    max_clipping_ratio: float = 0.01
    min_snr_db: float = 15.0  # below this the recording is rejected as noisy
    warn_snr_db: float = 25.0  # below this confidence is reduced
    edge_margin_s: float = 0.04  # speech touching the edge within this margin = possibly cut off


class RatingThresholds(BaseModel):
    """Progression thresholds (configurable, not clinical standards)."""

    mastered: int = 90  # and every sound rated "good"
    satisfactory: int = 70
    strong_error_below: int = 60  # any sound scoring below this -> "needs practice"
    cap_scores: bool = True  # keep the overall score consistent with the rating label


class PhonemeThresholds(BaseModel):
    """Phone status cut-offs on the calibrated (expected expert rating) scale.

    On speechocean762 a calibrated score below ~70 corresponds to roughly a
    35-50% chance that experts judged the sound wrong, below ~85 to ~10-30%.
    """

    good: int = 85
    fair: int = 70
    # A competing sound is reported only if it is at least this probable.
    report_substitution_min_prob: float = 0.30
    report_deletion_min_prob: float = 0.40


class ConfidenceThresholds(BaseModel):
    inconclusive_below: float = 0.35
    low_below: float = 0.60
    high_at_or_above: float = 0.80


class AnalysisConfig(BaseModel):
    engine: str = Field("auto", description="auto | allosaurus | wav2vec2 | none")
    allosaurus_model: str = "eng2102"
    wav2vec2_model: str = "facebook/wav2vec2-lv-60-espeak-cv-ft"
    model_dir: Path = REPO_ROOT / "models"
    weights: ScoreWeights = ScoreWeights()
    quality: QualityThresholds = QualityThresholds()
    rating: RatingThresholds = RatingThresholds()
    phoneme: PhonemeThresholds = PhonemeThresholds()
    confidence: ConfidenceThresholds = ConfidenceThresholds()
    calibration_file: Path | None = None
    tts_voices: list[str] = Field(
        default_factory=lambda: [
            "en_US-libritts_r-medium:0",
            "en_US-libritts_r-medium:40",
            "en_GB-vctk-medium:3",
        ],
        description="Piper voices used for reference audio, as <voice>[:<speaker id>].",
    )
    playback_voice: str = "en_US-libritts_r-medium:0"
    reference_cache_dir: Path = REPO_ROOT / "data" / "cache" / "reference_audio"
    human_reference_dir: Path = REPO_ROOT / "data" / "reference_audio"

    @classmethod
    def load(cls) -> AnalysisConfig:
        data: dict = {}
        path = os.environ.get("SPEECH_ANALYSIS_CONFIG")
        if path:
            data = json.loads(Path(path).read_text())
        cfg = cls.model_validate(data)
        env = os.environ
        if "SA_ENGINE" in env:
            cfg.engine = env["SA_ENGINE"]
        if "SA_MODEL_DIR" in env:
            cfg.model_dir = Path(env["SA_MODEL_DIR"])
        if "SA_WAV2VEC2_MODEL" in env:
            cfg.wav2vec2_model = env["SA_WAV2VEC2_MODEL"]
        for key in ScoreWeights.model_fields:
            env_key = f"SA_WEIGHT_{key.upper()}"
            if env_key in env:
                setattr(cfg.weights, key, float(env[env_key]))
        if "SA_RATING_MASTERED" in env:
            cfg.rating.mastered = int(env["SA_RATING_MASTERED"])
        if "SA_RATING_SATISFACTORY" in env:
            cfg.rating.satisfactory = int(env["SA_RATING_SATISFACTORY"])
        if "SA_TTS_VOICES" in env:
            cfg.tts_voices = [v.strip() for v in env["SA_TTS_VOICES"].split(",") if v.strip()]
        return cfg
