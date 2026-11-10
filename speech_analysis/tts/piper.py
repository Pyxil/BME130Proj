"""Piper (VITS) neural TTS executed directly with onnxruntime.

We feed Piper *phonemes* rather than text: each pronunciation variant in the
word database is converted from ARPAbet to espeak-style IPA, the phoneme
alphabet Piper voices were trained on.  This guarantees that the reference
audio realises exactly the variant being scored (e.g. British vs American
"tomato") without needing espeak-ng at runtime.

Voices are downloaded by ``scripts/download_models.py`` into
``models/piper/<voice>/<voice>.onnx`` (+ ``.onnx.json``).
"""

from __future__ import annotations

import json
import threading
import unicodedata
from pathlib import Path

import numpy as np

from ..phoneme_analysis.phonemes import split_stress

_ARPA_TO_ESPEAK = {
    "AA": "ɑː", "AE": "æ", "AH": "ʌ", "AO": "ɔː", "AW": "aʊ", "AY": "aɪ", "EH": "ɛ", "ER": "ɜː",
    "EY": "eɪ", "IH": "ɪ", "IY": "iː", "OW": "oʊ", "OY": "ɔɪ", "UH": "ʊ", "UW": "uː",
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "F": "f", "G": "ɡ", "HH": "h", "JH": "dʒ", "K": "k",
    "L": "l", "M": "m", "N": "n", "NG": "ŋ", "P": "p", "R": "ɹ", "S": "s", "SH": "ʃ", "T": "t",
    "TH": "θ", "V": "v", "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ",
}


def arpabet_to_espeak_ipa(arpabet: list[str], accent: str = "us") -> str:
    """ARPAbet -> espeak IPA string with stress marks before vowels (Piper input)."""
    out = []
    for p in arpabet:
        base, stress = split_stress(p)
        if base == "AH" and stress == 0:
            sym = "ə"
        elif base == "ER" and stress == 0:
            sym = "ɚ" if accent == "us" else "ə"
        elif base == "OW" and accent == "gb":
            sym = "əʊ"
        elif base == "AA" and accent == "gb":
            sym = "ɑː"
        else:
            sym = _ARPA_TO_ESPEAK[base]
        if stress == 1:
            sym = "ˈ" + sym
        elif stress == 2:
            sym = "ˌ" + sym
        out.append(sym)
    return "".join(out)


class PiperVoice:
    def __init__(self, model_path: Path, config_path: Path, threads: int = 1):
        import onnxruntime as ort  # optional dependency

        self.name = model_path.stem
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        self._session = ort.InferenceSession(str(model_path), so, providers=["CPUExecutionProvider"])
        self._lock = threading.Lock()
        self.id_map: dict[str, list[int]] = self.config["phoneme_id_map"]
        self.sample_rate: int = int(self.config["audio"]["sample_rate"])
        self.num_speakers: int = int(self.config.get("num_speakers", 1))
        self.espeak_voice: str = self.config.get("espeak", {}).get("voice", "en-us")
        self._input_names = {i.name for i in self._session.get_inputs()}

    @classmethod
    def from_dir(cls, voice_dir: Path) -> PiperVoice:
        models = sorted(voice_dir.glob("*.onnx"))
        if not models:
            raise FileNotFoundError(f"no .onnx model in {voice_dir}")
        model = models[0]
        cfg = model.with_suffix(".onnx.json")
        if not cfg.exists():
            raise FileNotFoundError(f"missing {cfg.name}")
        return cls(model, cfg)

    def phoneme_ids(self, ipa: str) -> list[int]:
        ids = list(self.id_map["^"]) + list(self.id_map["_"])
        for ch in unicodedata.normalize("NFD", ipa):
            if ch in self.id_map:
                ids.extend(self.id_map[ch])
                ids.extend(self.id_map["_"])
        ids.extend(self.id_map["$"])
        return ids

    def synthesize_ipa(self, ipa: str, speaker_id: int = 0, length_scale: float = 1.0,
                       noise_scale: float | None = None, noise_w: float | None = None) -> np.ndarray:
        """Synthesise espeak-IPA phonemes; returns float32 audio at ``sample_rate``."""
        inf = self.config.get("inference", {})
        scales = np.array(
            [
                inf.get("noise_scale", 0.667) if noise_scale is None else noise_scale,
                inf.get("length_scale", 1.0) * length_scale,
                inf.get("noise_w", 0.8) if noise_w is None else noise_w,
            ],
            dtype=np.float32,
        )
        ids = self.phoneme_ids(ipa)
        feeds = {
            "input": np.array([ids], dtype=np.int64),
            "input_lengths": np.array([len(ids)], dtype=np.int64),
            "scales": scales,
        }
        if "sid" in self._input_names:
            feeds["sid"] = np.array([min(max(speaker_id, 0), self.num_speakers - 1)], dtype=np.int64)
        with self._lock:
            audio = self._session.run(None, feeds)[0]
        audio = np.asarray(audio, dtype=np.float32).squeeze()
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak > 0:
            audio = audio / peak * 0.9
        return audio
