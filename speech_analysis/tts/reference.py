"""Resolve reference pronunciations for playback and acoustic comparison.

Priority for each (word, variant):

1. A human recording ``data/reference_audio/<word>[_<variant>].wav`` (best:
   e.g. recorded by a speech-language pathologist).
2. Piper neural TTS synthesised from the variant's phonemes.
3. espeak-ng formant synthesis from the word text (robotic but always works
   when espeak-ng is installed).

If none is available the API reports 404 and the frontend falls back to the
browser's speechSynthesis voice for playback; acoustic similarity is then
reported as unavailable rather than guessed.
"""

from __future__ import annotations

import hashlib
import io
import logging
import shutil
import subprocess
import threading
from dataclasses import dataclass

import numpy as np
import soundfile as sf

from ..audio_processing.io import resample
from ..config import AnalysisConfig
from .piper import PiperVoice, arpabet_to_espeak_ipa

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceSpec:
    voice: str
    speaker_id: int = 0

    @classmethod
    def parse(cls, s: str) -> VoiceSpec:
        name, _, sid = s.partition(":")
        return cls(name, int(sid) if sid else 0)

    def __str__(self) -> str:
        return f"{self.voice}:{self.speaker_id}"


@dataclass
class ReferenceAudio:
    audio: np.ndarray  # float32
    sr: int
    source: str  # human | piper | espeak
    voice: str | None
    variant_id: str


class ReferenceAudioService:
    def __init__(self, config: AnalysisConfig):
        self.config = config
        self._voices: dict[str, PiperVoice | None] = {}
        self._lock = threading.Lock()
        self._mem: dict[str, ReferenceAudio] = {}
        config.reference_cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ voices
    def _voice(self, name: str) -> PiperVoice | None:
        with self._lock:
            if name not in self._voices:
                voice_dir = self.config.model_dir / "piper" / name
                try:
                    self._voices[name] = PiperVoice.from_dir(voice_dir)
                except Exception as exc:  # noqa: BLE001
                    log.info("Piper voice %s unavailable: %s", name, exc)
                    self._voices[name] = None
            return self._voices[name]

    def available_voices(self) -> list[VoiceSpec]:
        specs = [VoiceSpec.parse(v) for v in self.config.tts_voices]
        return [s for s in specs if self._voice(s.voice) is not None]

    @staticmethod
    def espeak_available() -> bool:
        return shutil.which("espeak-ng") is not None

    def status(self) -> dict:
        return {
            "piper_voices": [str(v) for v in self.available_voices()],
            "espeak": self.espeak_available(),
            "human_recordings": sorted(p.stem for p in self.config.human_reference_dir.glob("*.wav"))[:200],
        }

    # --------------------------------------------------------------- synthesis
    @staticmethod
    def _slug(word: str) -> str:
        return "".join(c for c in word.lower() if c.isalnum() or c in "-_")

    def _human(self, word: str, variant_id: str) -> ReferenceAudio | None:
        d = self.config.human_reference_dir
        for name in (f"{self._slug(word)}_{variant_id}.wav", f"{self._slug(word)}.wav"):
            p = d / name
            if p.exists():
                y, sr = sf.read(p, dtype="float32", always_2d=True)
                return ReferenceAudio(y.mean(axis=1), sr, "human", None, variant_id)
        return None

    def _piper(self, word: str, variant: dict, spec: VoiceSpec, length_scale: float) -> ReferenceAudio | None:
        voice = self._voice(spec.voice)
        if voice is None:
            return None
        accent = "gb" if variant["id"].startswith("gb") or spec.voice.startswith("en_GB") else "us"
        ipa = arpabet_to_espeak_ipa(variant["arpabet"], accent=accent)
        key = hashlib.sha1(f"{spec}|{ipa}|{length_scale}".encode()).hexdigest()[:16]
        path = self.config.reference_cache_dir / f"{self._slug(word)}_{variant['id']}_{key}.wav"
        if path.exists():
            y, sr = sf.read(path, dtype="float32")
            return ReferenceAudio(y, sr, "piper", str(spec), variant["id"])
        y = voice.synthesize_ipa(ipa, speaker_id=spec.speaker_id, length_scale=length_scale,
                                 noise_scale=0.333, noise_w=0.333)
        try:
            sf.write(path, y, voice.sample_rate, subtype="PCM_16")
        except OSError as exc:
            log.warning("could not cache reference audio: %s", exc)
        return ReferenceAudio(y, voice.sample_rate, "piper", str(spec), variant["id"])

    def _espeak(self, word: str, variant_id: str, slow: bool) -> ReferenceAudio | None:
        exe = shutil.which("espeak-ng")
        if exe is None:
            return None
        voice = "en-gb" if variant_id.startswith("gb") else "en-us"
        proc = subprocess.run([exe, "-v", voice, "-s", "110" if slow else "150", "--stdout", word],
                              capture_output=True, timeout=10, check=False)
        if proc.returncode != 0 or not proc.stdout:
            return None
        y, sr = sf.read(io.BytesIO(proc.stdout), dtype="float32", always_2d=True)
        return ReferenceAudio(y.mean(axis=1), sr, "espeak", voice, variant_id)

    # ------------------------------------------------------------------ public
    def playback(self, word: str, variant: dict, slow: bool = False) -> ReferenceAudio | None:
        """Audio for the 'Hear pronunciation' button."""
        human = self._human(word, variant["id"])
        if human is not None:
            return human
        spec = VoiceSpec.parse(self.config.playback_voice)
        if variant["id"].startswith("gb"):
            gb = [v for v in self.available_voices() if v.voice.startswith("en_GB")]
            spec = gb[0] if gb else spec
        ref = self._piper(word, variant, spec, 1.45 if slow else 1.1)
        return ref or self._espeak(word, variant["id"], slow)

    def references_for_pronunciation(self, word: str, variant_id: str, arpabet: list[str]) -> list[ReferenceAudio]:
        """16 kHz recordings of an arbitrary pronunciation (e.g. a common mistake) in every standard voice.

        Not kept in memory: callers keep the features they need, and the audio is cached on disk.
        """
        out = []
        for spec in self.available_voices():
            r = self._piper(word, {"id": variant_id, "arpabet": list(arpabet)}, spec, 1.0)
            if r is not None:
                out.append(ReferenceAudio(resample(r.audio, r.sr, 16000), 16000, r.source, r.voice, r.variant_id))
        return out

    def references_for_scoring(self, word: str, variants: list[dict], keep_in_memory: bool = True) -> list[ReferenceAudio]:
        """16 kHz references used for DTW similarity (several voices per variant)."""
        refs: list[ReferenceAudio] = []
        for variant in variants:
            human = self._human(word, variant["id"])
            if human is not None:
                refs.append(human)
            for spec in self.available_voices():
                key = f"{word}|{variant['id']}|{spec}"
                r = self._mem.get(key) or self._piper(word, variant, spec, 1.0)
                if r is None:
                    continue
                if keep_in_memory:
                    self._mem[key] = r
                refs.append(r)
        if not refs:
            for variant in variants[:1]:
                r = self._espeak(word, variant["id"], slow=False)
                if r is not None:
                    refs.append(r)
        out = []
        for r in refs:
            out.append(ReferenceAudio(resample(r.audio, r.sr, 16000), 16000, r.source, r.voice, r.variant_id))
        return out
