"""Thin service wrapper around :mod:`speech_analysis` (singleton, concurrency limit).

Routes depend on :func:`get_analysis_service`, so tests can override it with a
fake that needs no audio models.
"""

from __future__ import annotations

import json
import logging
import threading

from speech_analysis.audio_processing.io import encode_wav
from speech_analysis.contracts import AnalysisResult
from speech_analysis.pipeline import PronunciationAnalyzer

from ..core.config import get_settings

log = logging.getLogger(__name__)


class AnalysisService:
    def __init__(self) -> None:
        settings = get_settings()
        vocab = json.loads(settings.words_file.read_text(encoding="utf-8"))["words"]
        self.analyzer = PronunciationAnalyzer(vocabulary=vocab)
        self._sem = threading.BoundedSemaphore(settings.max_concurrent_analyses)

    def analyze(self, audio: bytes, word: dict) -> AnalysisResult:
        with self._sem:
            return self.analyzer.analyze(audio, word)

    def reference_audio(self, word: dict, variant_id: str, slow: bool) -> tuple[bytes, str] | None:
        variant = next((v for v in word["variants"] if v["id"] == variant_id), word["variants"][0])
        ref = self.analyzer.references.playback(word["word"], variant, slow=slow)
        if ref is None:
            return None
        return encode_wav(ref.audio, ref.sr), ref.source

    def status(self) -> dict:
        info = self.analyzer.engine_info().model_dump()
        cfg = self.analyzer.config
        info["weights"] = (cfg.signal.weights if self.analyzer.engine is None else cfg.weights).model_dump()
        if self.analyzer.engine is None:  # how the signal scorer did on unseen voices (calibration file)
            info["validation"] = self.analyzer.signal_calibration.validation
        info["rating_thresholds"] = self.analyzer.config.rating.model_dump()
        return info

    def reference_status(self) -> dict:
        return self.analyzer.references.status()

    def warmup(self) -> None:
        try:
            _ = self.analyzer.engine
            _ = self.analyzer.phone_calibration
            self.analyzer.references.available_voices()
            log.info("analysis engine ready: %s", self.analyzer.engine_info().name)
            if self.analyzer.engine is None:  # signal analysis: prepare every word's standards
                self.analyzer.standards.warm()
                log.info("standard recordings ready for %d words", self.analyzer.standards.words_ready)
        except Exception as exc:  # noqa: BLE001
            log.warning("analysis warm-up failed: %s", exc)


_service: AnalysisService | None = None
_lock = threading.Lock()


def get_analysis_service() -> AnalysisService:
    global _service
    with _lock:
        if _service is None:
            _service = AnalysisService()
    return _service
