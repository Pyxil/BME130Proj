"""Standard recordings for every practice word, plus word identification by template matching.

Standards are the reference pronunciations: human recordings dropped into
``data/reference_audio/`` when available, and generated voices (Piper) for
every pronunciation variant of the word. Their features are computed once and
kept in memory.

Word identification compares a recording with the standards of *every* word
and ranks the words by aligned spectral distance: it answers "which word does
this waveform look like?" using nothing but the microphone signal.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

import numpy as np

from ..tts.reference import ReferenceAudioService
from .compare import Standard, distance_only
from .features import SignalFeatures, extract
from .minimal_pairs import Mistake, mistakes_for
from .segments import segment, syllable_nuclei

log = logging.getLogger(__name__)

SYLLABLE_PENALTY = 0.04  # distance added per syllable of difference: a small tie-breaker. On held-out voices
# it made no meaningful difference (top-1 77.6% with it, 77.9% without, docs/validation.md).


@dataclass
class Identification:
    ranked: list[tuple[str, float]] = field(default_factory=list)  # (word, distance), closest first
    target_rank: int | None = None  # 1 = the target word is the closest match
    words_compared: int = 0


class StandardLibrary:
    def __init__(self, references: ReferenceAudioService, vocabulary: list[dict]):
        self.references = references
        self.vocabulary = vocabulary
        self._by_word: dict[str, list[Standard]] = {}
        self._mistakes: dict[str, list[tuple[Mistake, list[Standard]]]] = {}
        self._lock = threading.Lock()
        self._warm_thread: threading.Thread | None = None

    def for_word(self, word: dict) -> list[Standard]:
        """Standards of one word (computed on first use, then cached)."""
        with self._lock:
            hit = self._by_word.get(word["word"])
        if hit is not None:
            return hit
        variants = {v["id"]: v for v in word["variants"]}
        out = []
        for ref in self.references.references_for_scoring(word["word"], word["variants"], keep_in_memory=False):
            f = _compact(extract(ref.audio))
            arpa = variants.get(ref.variant_id, word["variants"][0])["arpabet"]
            out.append(Standard(word["word"], ref.variant_id, ref.source, ref.voice, f, segment(f, arpa),
                                len(syllable_nuclei(f))))
        with self._lock:
            self._by_word[word["word"]] = out
        return out

    def mistakes(self, word: dict) -> list[tuple[Mistake, list[Standard]]]:
        """Standards of the word's common mistakes, one per standard voice (minimal pairs)."""
        with self._lock:
            hit = self._mistakes.get(word["word"])
        if hit is not None:
            return hit
        primary = word["variants"][0]
        out = []
        for m in mistakes_for(primary["arpabet"]):
            stds = [Standard(word["word"], f"mistake-{m.key}", r.source, r.voice, _compact(extract(r.audio)), [])
                    for r in self.references.references_for_pronunciation(
                        word["word"], f"{primary['id']}-mistake-{m.key}", list(m.arpabet))]
            if stds:
                out.append((m, stds))
        with self._lock:
            self._mistakes[word["word"]] = out
        return out

    @property
    def words_ready(self) -> int:
        with self._lock:
            return sum(1 for v in self._by_word.values() if v)

    def warm(self) -> None:
        """Prepare the standards of every word and its common mistakes (a few minutes the first time,
        then cached on disk)."""
        for w in self.vocabulary:
            try:
                self.for_word(w)
                self.mistakes(w)
            except Exception as exc:  # noqa: BLE001 - one bad word must not stop the rest
                log.warning("standards for %r unavailable: %s", w.get("word"), exc)

    def warm_in_background(self) -> None:
        with self._lock:
            if self._warm_thread is None and self.vocabulary:
                self._warm_thread = threading.Thread(target=self.warm, name="standards-warmup", daemon=True)
                self._warm_thread.start()

    def identify(self, user: SignalFeatures, warp: float, top: int = 3, target: str | None = None,
                 step: int = 2, syllable_penalty: float = SYLLABLE_PENALTY) -> Identification:
        """Rank the words whose standards are ready by distance to ``user`` (closest first).

        Uses the speaker's warp factor found for the target word, every
        ``step``-th frame (20 ms) for speed, and skips standards whose length
        differs too much from the recording to be the same word. Each
        difference between the number of loudness peaks (syllables) in the
        recording and in a standard adds ``syllable_penalty`` to the distance.
        """
        with self._lock:
            items = [(w, s) for w, s in self._by_word.items() if s]
        us, ue = user.speech_bounds()
        n_user = len(syllable_nuclei(user))
        sub = _Subsampled(user, step)
        scores = []
        for word, stds in items:
            best = np.inf
            for s in stds:
                ss, se = s.features.speech_bounds()
                if not 0.4 <= (ue - us) / max(1, se - ss) <= 2.6:
                    continue
                d = distance_only(sub, _Subsampled(s.features, step), warp)
                best = min(best, d + syllable_penalty * abs(n_user - s.syllables))
            if np.isfinite(best):
                scores.append((float(best), word))
        scores.sort()
        rank = next((k + 1 for k, (_, w) in enumerate(scores) if w == target), None) if target else None
        return Identification([(w, d) for d, w in scores[:top]], rank, len(items))


def _compact(f: SignalFeatures) -> SignalFeatures:
    """Keep only what a standard needs: standards are always used unwarped, so compute those
    features now and drop the power spectrum (most of the memory)."""
    f.spectral(1.0)
    f.power = None
    return f


class _Subsampled:
    """Every ``step``-th frame of a recording's spectral features (duck-types SignalFeatures.spectral)."""

    def __init__(self, f: SignalFeatures, step: int):
        self.f, self.step = f, step

    def spectral(self, alpha: float = 1.0) -> np.ndarray:
        return self.f.spectral(alpha)[:: self.step]
