"""Engine registry.

``create_engine`` returns the first available engine for the configured name.
``"auto"`` prefers Allosaurus (validated on speechocean762) and returns
``None`` when no phoneme model is installed; the pipeline then runs in the
clearly-labelled *acoustic baseline* mode without phoneme-level scores.
"""

from __future__ import annotations

import logging

from ...config import AnalysisConfig
from .base import EngineOutput, EngineUnavailable, PhoneAssessment, PhonemeEngine, VariantAssessment

log = logging.getLogger(__name__)

__all__ = [
    "EngineOutput", "EngineUnavailable", "PhoneAssessment", "PhonemeEngine", "VariantAssessment",
    "create_engine", "available_engines",
]


def _allosaurus(cfg: AnalysisConfig) -> PhonemeEngine:
    from .allosaurus_engine import AllosaurusEngine

    return AllosaurusEngine(cfg.model_dir, model=cfg.allosaurus_model)


def _wav2vec2(cfg: AnalysisConfig) -> PhonemeEngine:
    from .wav2vec2_engine import Wav2Vec2Engine

    return Wav2Vec2Engine(cfg.wav2vec2_model)


ENGINES = {"allosaurus": _allosaurus, "wav2vec2": _wav2vec2}


def create_engine(cfg: AnalysisConfig) -> PhonemeEngine | None:
    if cfg.engine in ("signal", "none"):  # signals-and-systems comparison, no phoneme model
        return None
    order = ["allosaurus", "wav2vec2"] if cfg.engine == "auto" else [cfg.engine]
    errors = []
    for name in order:
        factory = ENGINES.get(name)
        if factory is None:
            raise ValueError(f"unknown engine {name!r}; choose from {sorted(ENGINES)} or 'signal'")
        try:
            engine = factory(cfg)
            log.info("phoneme engine: %s (%s)", engine.name, engine.model)
            return engine
        except EngineUnavailable as exc:
            errors.append(f"{name}: {exc}")
    if cfg.engine != "auto":
        raise EngineUnavailable("; ".join(errors))
    log.warning("No phoneme engine available, running acoustic baseline only. %s", "; ".join(errors))
    return None


def available_engines() -> list[str]:
    return sorted(ENGINES)
