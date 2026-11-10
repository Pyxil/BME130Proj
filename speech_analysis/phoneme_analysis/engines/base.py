"""Phoneme engine interface.

An engine turns 16 kHz audio plus candidate pronunciations into phoneme-level
evidence.  To plug in a new model (e.g. a pronunciation-assessment model
fine-tuned on clinical data) implement :class:`PhonemeEngine` and register it
in :mod:`speech_analysis.phoneme_analysis.engines`.  Nothing downstream
(scoring, API, frontend) needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


class EngineUnavailable(RuntimeError):
    """Raised when an engine's dependencies or model files are missing."""


@dataclass
class PhoneAssessment:
    index: int
    arpabet: str
    posterior: float  # P(expected phone or an accepted variant)
    strict_posterior: float  # P(expected phone exactly)
    best_alternative: str | None  # ARPAbet label of the strongest competitor; None = deletion
    best_alternative_prob: float
    deletion_prob: float
    accepted_variant: str | None = None
    start_s: float | None = None
    end_s: float | None = None


@dataclass
class VariantAssessment:
    variant_id: str
    arpabet: list[str]
    log_likelihood: float
    phones: list[PhoneAssessment]


@dataclass
class EngineOutput:
    engine: str
    model: str
    best: VariantAssessment
    variants: list[VariantAssessment]
    decoded_ipa: list[str]
    frames: int
    frame_rate: float
    recognized_word: str | None = None
    recognized_matches_target: bool | None = None
    recognition_margin: float | None = None  # log-likelihood gap to the best non-target word
    phoneme_error_rate: float | None = None
    posteriorgram: np.ndarray | None = None  # (T, V) probabilities, for posteriorgram DTW
    extras: dict = field(default_factory=dict)


class PhonemeEngine(ABC):
    name: str = "base"
    model: str = ""
    phoneme_level: bool = True
    calibration_id: str | None = None

    @abstractmethod
    def assess(self, audio: np.ndarray, variants: list[dict], vocabulary: list[dict] | None = None,
               target_word: str | None = None) -> EngineOutput:
        """Assess ``audio`` (float32, 16 kHz) against pronunciation ``variants``.

        ``variants`` are word-database variant dicts (``id``, ``arpabet``).
        ``vocabulary`` optionally lists other practice words (``word``,
        ``variants``) for closed-vocabulary word recognition.
        """

    def warmup(self) -> None:  # pragma: no cover - optional
        return None
