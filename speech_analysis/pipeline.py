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
from .calibration import load_dtw_calibration, load_phone_calibration, load_signal_calibration
from .config import REPO_ROOT, AnalysisConfig
from .contracts import AnalysisResult, EngineInfo
from .feature_extraction import pitch, syllable_nuclei
from .phoneme_analysis.engines import PhonemeEngine, create_engine
from .phoneme_analysis.phonemes import syllable_count
from .scoring.acoustic_similarity import acoustic_similarity
from .scoring.components import syllable_completeness, temporal_score
from .scoring.scorer import Evidence, build_result
from .signal_analysis.compare import compare, mistake_contrasts, pick_best
from .signal_analysis.features import extract, frames_to_seconds
from .signal_analysis.report import build_signal_result
from .signal_analysis.segments import syllable_nuclei as signal_nuclei
from .signal_analysis.standards import StandardLibrary
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
        self._standards: StandardLibrary | None = None

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

    @property
    def standards(self) -> StandardLibrary:
        """Standard recordings of every word (signal mode)."""
        if self._standards is None:
            self._standards = StandardLibrary(self.references, self.vocabulary)
        return self._standards

    @cached_property
    def signal_calibration(self):
        return load_signal_calibration()

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
                name="signal-analysis", model=None, phoneme_level=False, calibration=self.signal_calibration.source,
                notes="Scores compare the recording's waveform features (spectrum, loudness, pitch, timing) with "
                      "standard recordings using signal processing. No speech-recognition model is used, so "
                      "feedback names parts of the word rather than individual sounds.")
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

        if self.engine is None:
            return self._analyze_signal(prepared, word, info, analysis_id, t0)

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

    # ------------------------------------------------------- signal analysis
    def _analyze_signal(self, prepared, word: dict, info: EngineInfo, analysis_id: str, t0: float) -> AnalysisResult:
        """Signals-and-systems path: compare the recording with the word's standard recordings."""
        user = extract(prepared.audio)
        try:
            standards = self.standards.for_word(word)
        except Exception as exc:  # noqa: BLE001 - reported as inconclusive below
            log.warning("standard recordings unavailable: %s", exc)
            standards = []
        if not standards:
            return AnalysisResult(
                analysis_id=analysis_id, word=word["word"], word_id=word.get("id"), status="inconclusive",
                confidence=0.0, confidence_label="low", needs_retry=True, quality=prepared.quality, engine=info,
                retry_reason="No standard recording is available for this word yet (run scripts/download_models.py).",
                processing_ms=int((time.perf_counter() - t0) * 1000))
        best = pick_best([compare(user, s) for s in standards])
        ident = None
        if self.config.signal.identify_words and self.vocabulary:
            self.standards.warm_in_background()
            ident = self.standards.identify(user, best.warp, top=3, target=word["word"])

        try:
            contrasts = mistake_contrasts(user, best.warp, standards, self.standards.mistakes(word))
        except Exception as exc:  # noqa: BLE001 - the minimal-pair check is optional
            log.warning("minimal-pair standards unavailable: %s", exc)
            contrasts = []

        variant = next((v for v in word["variants"] if v["id"] == best.standard.variant_id), word["variants"][0])
        syl = syllable_completeness(syllable_count(variant["arpabet"]), len(signal_nuclei(user)))
        us, ue = user.speech_bounds()
        ss, se = best.standard.features.speech_bounds()
        tscore, timing = temporal_score(frames_to_seconds(ue - us), frames_to_seconds(se - ss), best.tempo_deviation)
        return build_signal_result(
            word=word, quality=prepared.quality, info=info, comp=best, standards_compared=len(standards),
            user=user, syllables=syl, timing=timing, temporal=tscore, ident=ident, contrasts=contrasts,
            vocab_size=len(self.vocabulary), cfg=self.config, cal=self.signal_calibration,
            analysis_id=analysis_id, processing_ms=int((time.perf_counter() - t0) * 1000))
