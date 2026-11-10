"""wav2vec 2.0 phoneme recogniser (espeak IPA vocabulary) as a CTC engine.

Default model: ``facebook/wav2vec2-lv-60-espeak-cv-ft`` (Xu et al., 2021;
Apache-2.0), a 300M-parameter model fine-tuned for phoneme recognition with
espeak-ng IPA labels.  It works on 16 kHz audio (full band), so it is expected
to discriminate fricatives better than the 8 kHz Allosaurus model.

STATUS: implemented and unit-tested with a stub model, but NOT validated on
real data in the development environment (the Hugging Face hub was not
reachable there).  Validate it with ``scripts/evaluate_speechocean762.py``
before making it the default.  Select it with ``SA_ENGINE=wav2vec2``.
"""

from __future__ import annotations

import os

import numpy as np

from .base import EngineUnavailable
from .ctc_engine import CTCPhonemeEngine

# Candidate label -> espeak IPA token options in preference order.  Options are
# resolved against the model vocabulary at load time; multi-symbol options
# fall back to per-character tokens when the vocabulary splits them.
_OPTIONS: dict[str, list[str]] = {
    "AA": ["ɑː", "ɑ"], "AE": ["æ"], "AH": ["ʌ"], "AH0": ["ə"], "AO": ["ɔː", "ɔ"],
    "AW": ["aʊ"], "AY": ["aɪ"], "EH": ["ɛ"], "ER": ["ɚ", "ɜː", "ɝ"], "EY": ["eɪ"],
    "IH": ["ɪ"], "IY": ["iː", "i"], "OW": ["oʊ", "əʊ"], "OY": ["ɔɪ"], "UH": ["ʊ"], "UW": ["uː", "u"],
    "B": ["b"], "CH": ["tʃ"], "D": ["d"], "DH": ["ð"], "F": ["f"], "G": ["ɡ", "g"], "HH": ["h"],
    "JH": ["dʒ"], "K": ["k"], "L": ["l"], "M": ["m"], "N": ["n"], "NG": ["ŋ"], "P": ["p"],
    "R": ["ɹ", "r"], "S": ["s"], "SH": ["ʃ"], "T": ["t", "ɾ", "ʔ"], "TH": ["θ"], "V": ["v"], "W": ["w"],
    "Y": ["j"], "Z": ["z"], "ZH": ["ʒ"],
}


def resolve_units(vocab: dict[str, int]) -> dict[str, list[tuple[int, ...]]]:
    """Map candidate labels to token-id units available in ``vocab``."""
    out: dict[str, list[tuple[int, ...]]] = {}
    for label, options in _OPTIONS.items():
        units: list[tuple[int, ...]] = []
        for opt in options:
            if opt in vocab:
                units.append((vocab[opt],))
            elif all(ch in vocab for ch in opt):
                units.append(tuple(vocab[ch] for ch in opt))
        if not units:
            raise EngineUnavailable(f"vocabulary lacks tokens for {label}")
        out[label] = list(dict.fromkeys(units))
    return out


class Wav2Vec2Engine(CTCPhonemeEngine):
    name = "wav2vec2"
    phoneme_level = True
    frame_rate = 50.0  # 20 ms frames

    def __init__(self, model_id: str, threads: int = 2, allow_download: bool | None = None,
                 _model=None, _vocab: dict[str, int] | None = None, _processor=None):
        super().__init__()
        self.model = model_id
        if allow_download is None:
            allow_download = os.environ.get("SA_ALLOW_MODEL_DOWNLOAD", "0") == "1"
        if _model is not None:  # injection point for tests
            self._model, vocab, self._processor = _model, _vocab, _processor
            import torch

            self._torch = torch
        else:
            try:
                import torch
                from transformers import AutoFeatureExtractor, Wav2Vec2ForCTC
            except ImportError as exc:  # pragma: no cover
                raise EngineUnavailable("wav2vec2 engine needs `pip install -e .[ml]` (torch, transformers)") from exc
            torch.set_num_threads(threads)
            self._torch = torch
            try:
                self._processor = AutoFeatureExtractor.from_pretrained(model_id, local_files_only=not allow_download)
                self._model = Wav2Vec2ForCTC.from_pretrained(model_id, local_files_only=not allow_download).eval()
                from huggingface_hub import hf_hub_download

                vocab_path = hf_hub_download(model_id, "vocab.json", local_files_only=not allow_download)
            except Exception as exc:  # noqa: BLE001
                raise EngineUnavailable(
                    f"wav2vec2 model {model_id} not available locally. Run: python scripts/download_models.py --wav2vec2"
                ) from exc
            import json

            vocab = json.load(open(vocab_path, encoding="utf-8"))
        self.blank = int(vocab.get("<pad>", 0))
        self._token_names = {i: t for t, i in vocab.items()}
        for label, units in resolve_units(vocab).items():
            self._register(label, units[0], units[1:])
        self.calibration_id = f"wav2vec2-{model_id.split('/')[-1]}"

    def log_posteriors(self, audio: np.ndarray) -> np.ndarray:
        torch = self._torch
        if self._processor is not None:
            inputs = self._processor(audio, sampling_rate=16000, return_tensors="pt").input_values
        else:
            x = (audio - audio.mean()) / (audio.std() + 1e-7)
            inputs = torch.from_numpy(x.astype(np.float32))[None]
        with torch.no_grad():
            logits = self._model(inputs).logits[0]
        return torch.log_softmax(logits.double(), dim=-1).numpy()
