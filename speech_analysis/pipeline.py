"""End-to-end pronunciation analysis pipeline.

    analyzer = PronunciationAnalyzer()                 # loads engine + references lazily
    result = analyzer.analyze(wav_bytes, word_entry)   # -> AnalysisResult

``word_entry`` is an entry of ``data/words.json`` (dict with ``word``,
``arpabet``, ``variants`` ...).  The analyzer is thread-safe and intended to
be created once per process.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from functools import cached_property
from pathlib import Path

import numpy as np

from .audio_processing import decode_audio, prepare_audio
from .audio_processing.preprocess import detect_speech
from .calibration import load_dtw_calibration, load_phone_calibration
from .config import REPO_ROOT, AnalysisConfig
from .contracts import AnalysisResult, EngineInfo
from .feature_extraction import pitch, syllable_nuclei
from .phoneme_analysis.engines import PhonemeEngine, create_engine
from .phoneme_analysis.phonemes import syllable_count
from .scoring.acoustic_similarity import acoustic_similarity
from .scoring.components import syllable_completeness, temporal_score
from .scoring.scorer import Evidence, build_result
from .tts.reference import ReferenceAudioService

log = logging.getLogger(__name__)
_SENTINEL = object()


def load_words(path: Path | None = None) -> list[dict]:
    path = path or REPO_ROOT / "data" / "words.json"
    return json.loads(Path(path).read_text(encoding="utf-8"))["words"]


class PronunciationAnalyzer:
    def __init__(self, config: AnalysisConfig | None = None, engine=_SENTINEL,
                 references: ReferenceAudioService | None = None, vocabulary: list[dict] | None = None):
        self.config = config or AnalysisConfig.load()
        self._engine = engine
        self._references = references
        self._vocabulary = vocabulary

    # Lazily created so that importing the backend stays fast.
    @property
    def engine(self) -> PhonemeEngine | None:
        if self._engine is _SENTINEL:
            self._engine = create_engine(self.config)
        return self._engine

    @property
    def references(self) -> ReferenceAudioService:
        if self._references is None:
            self._references = ReferenceAudioService(self.config)
        return self._references

    @property
    def vocabulary(self) -> list[dict]:
        if self._vocabulary is None:
            try:
                self._vocabulary = load_words()
            except FileNotFoundError:
                self._vocabulary = []
        return self._vocabulary

    @cached_property
    def phone_calibration(self):
        eng = self.engine
        return load_phone_calibration(eng.calibration_id if eng else None, self.config.calibration_file)

    @cached_property
    def dtw_calibration(self):
        return load_dtw_calibration()

    def engine_info(self) -> EngineInfo:
        eng = self.engine
        if eng is None:
            return EngineInfo(
                name="acoustic-baseline", model=None, phoneme_level=False, calibration=None,
                notes="No phoneme recognition model installed: phoneme-level scores are unavailable. "
                      "Scores use acoustic similarity, syllable and timing measures only.")
        cal = self.phone_calibration
        return EngineInfo(name=eng.name, model=eng.model, phoneme_level=eng.phoneme_level,
                          calibration=cal.source if cal else None,
                          notes=None if cal else "Uncalibrated: phone score = 100 x posterior.")

    # ------------------------------------------------------------------ main
    def analyze(self, audio: bytes | np.ndarray, word: dict, sr: int | None = None) -> AnalysisResult:
        t0 = time.perf_counter()
        analysis_id = str(uuid.uuid4())
        if isinstance(audio, (bytes, bytearray)):
            y, sr = decode_audio(bytes(audio))
        else:
            if sr is None:
                raise ValueError("sr is required for array input")
            from .audio_processing.io import resample

            y, sr = resample(np.asarray(audio, dtype=np.float32), sr), 16000
        prepared = prepare_audio(y, sr, self.config.quality)
        info = self.engine_info()
        if not prepared.quality.usable:
            ev = Evidence(word, prepared.quality, None, info, None, None, None, None)
            return build_result(ev, self.config, None, analysis_id, int((time.perf_counter() - t0) * 1000))

        speech = prepared.audio
        variants = word["variants"]
        engine_out = None
        if self.engine is not None:
            vocab = self.vocabulary if self.vocabulary else None
            engine_in = prepared.engine_audio if prepared.engine_audio is not None else speech
            engine_out = self.engine.assess(engine_in, variants, vocabulary=vocab, target_word=word["word"])
        best_variant_id = engine_out.best.variant_id if engine_out else variants[0]["id"]
        best_variant = next(v for v in variants if v["id"] == best_variant_id)

        refs = []
        try:
            refs = self.references.references_for_scoring(word["word"], variants)
        except Exception as exc:  # noqa: BLE001 - references are optional
            log.warning("reference audio unavailable: %s", exc)
        dcal = self.dtw_calibration
        sim = acoustic_similarity(speech, refs, variant_ids={best_variant_id},
                                  **({"midpoint": dcal.midpoint, "scale": dcal.scale} if dcal else {}))

        pc = pitch(speech)
        n_nuclei, _ = syllable_nuclei(speech, 16000, pc.voiced_prob)
        syl = syllable_completeness(syllable_count(best_variant["arpabet"]), n_nuclei,
                                    engine_out.best if engine_out else None)
        ref_durs = []
        for r in refs:
            if r.variant_id == best_variant_id:
                region = detect_speech(r.audio, 16000)
                if region is not None:
                    ref_durs.append((region.end - region.start) / 16000)
        ref_dur = float(np.median(ref_durs)) if ref_durs else None
        tscore, timing = temporal_score(prepared.quality.speech_duration_s, ref_dur,
                                        sim.tempo_deviation if sim else None)
        ev = Evidence(word, prepared.quality, engine_out, info, sim, syl, timing, tscore)
        result = build_result(ev, self.config, self.phone_calibration if engine_out else None,
                              analysis_id, int((time.perf_counter() - t0) * 1000))
        if result.components:
            result.components[0].details["pitch"] = pc.summary()
        return result
