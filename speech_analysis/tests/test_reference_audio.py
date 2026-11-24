"""Standard recordings are reproducible: noise off, and a fresh standard equals its cached copy."""

import numpy as np

from speech_analysis.config import AnalysisConfig
from speech_analysis.tts.reference import ReferenceAudioService, VoiceSpec


class FakeVoice:
    sample_rate = 22050

    def __init__(self):
        self.calls = []

    def synthesize_ipa(self, ipa, speaker_id=0, length_scale=1.0, noise_scale=None, noise_w=None):
        self.calls.append((noise_scale, noise_w))
        t = np.arange(int(0.3 * self.sample_rate)) / self.sample_rate
        return (0.9 * np.sin(2 * np.pi * 220.0 * t) + 1e-6).astype(np.float32)  # not exact in 16 bits


def service(tmp_path):
    svc = ReferenceAudioService(AnalysisConfig(reference_cache_dir=tmp_path))
    voice = FakeVoice()
    svc._voices["fake"] = voice
    return svc, voice


VARIANT = {"id": "us", "arpabet": ["R", "AE1", "B", "IH0", "T"]}


def test_standard_has_no_random_variation_and_cached_copy_is_identical(tmp_path):
    svc, voice = service(tmp_path)
    fresh = svc._piper("rabbit", VARIANT, VoiceSpec("fake"), 1.0, standard=True)
    cached = svc._piper("rabbit", VARIANT, VoiceSpec("fake"), 1.0, standard=True)
    assert voice.calls == [(0.0, 0.0)]  # synthesised once, without noise; the second call read the cache
    assert np.array_equal(fresh.audio, cached.audio)
    assert [p.suffix for p in tmp_path.iterdir()] == [".wav"]  # no temporary files left behind


def test_playback_keeps_natural_variation(tmp_path):
    svc, voice = service(tmp_path)
    svc._piper("rabbit", VARIANT, VoiceSpec("fake"), 1.1)
    assert voice.calls[0][0] > 0 and voice.calls[0][1] > 0
