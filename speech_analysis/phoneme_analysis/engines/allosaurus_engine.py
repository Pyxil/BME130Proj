"""Allosaurus phone recogniser as a CTC phoneme engine.

Allosaurus (Li et al., ICASSP 2020; GPL-3.0) is a pretrained phone recogniser
trained on 2000+ hours across 12 languages.  ``eng2102`` is its English model
with a 38-phone inventory.  Its frame-level CTC posteriors feed the
substitution-aware GOP in :mod:`speech_analysis.phoneme_analysis.ctc_gop`.

Known limitations (see docs/validation.md): the model works on 8 kHz
telephone-band features, so cues above 4 kHz (e.g. /s/ vs /θ/) are weakened;
diphthongs are written with glides (/aɪ/ = ``a j``).

Model files are fetched by ``scripts/download_models.py`` from the official
GitHub release; nothing is downloaded at request time.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import numpy as np

from .base import EngineUnavailable
from .ctc_engine import CTCPhonemeEngine

# ARPAbet candidate label -> preferred Allosaurus unit(s) and accepted tokenisation alternates.
_UNITS: dict[str, list[list[str]]] = {
    "AA": [["ɑ"]], "AE": [["æ"]], "AH": [["ʌ"]], "AH0": [["ə"]], "AO": [["ɔ"]],
    "AW": [["a", "w"], ["a", "ʊ"]], "AY": [["a", "j"], ["a", "ɪ"]], "EH": [["ɛ"]],
    "ER": [["ɹ̩"], ["ə", "ɹ"]], "EY": [["e", "j"], ["e"]], "IH": [["ɪ"]], "IY": [["i"]],
    "OW": [["o", "w"], ["o"]], "OY": [["ɔ", "j"], ["o", "j"]], "UH": [["ʊ"]], "UW": [["u"]],
    "B": [["b"]], "CH": [["t͡ʃ"]], "D": [["d"]], "DH": [["ð"]], "F": [["f"]], "G": [["ɡ"]],
    "HH": [["h"]], "JH": [["d͡ʒ"]], "K": [["k"]], "L": [["l"]], "M": [["m"]], "N": [["n"]],
    "NG": [["ŋ"]], "P": [["p"]], "R": [["ɹ"]], "S": [["s"]], "SH": [["ʃ"]], "T": [["t"]],
    "TH": [["θ"]], "V": [["v"]], "W": [["w"]], "Y": [["j"]], "Z": [["z"]], "ZH": [["ʒ"]],
}


class AllosaurusEngine(CTCPhonemeEngine):
    name = "allosaurus"
    phoneme_level = True

    def __init__(self, model_dir: Path, model: str = "eng2102", threads: int = 2):
        super().__init__()
        self.model = model
        model_path = Path(model_dir) / "allosaurus" / model
        if not (model_path / "model.pt").exists():
            raise EngineUnavailable(
                f"Allosaurus model not found at {model_path}. Run: python scripts/download_models.py --allosaurus"
            )
        try:
            import torch
            from allosaurus.am.factory import read_am
            from allosaurus.pm.factory import read_pm
        except ImportError as exc:  # pragma: no cover - depends on install
            raise EngineUnavailable("Allosaurus engine needs `pip install -e .[ml]` (torch, allosaurus)") from exc
        torch.set_num_threads(threads)
        self._torch = torch
        cfg = Namespace(model=model, device_id=-1, lang="ipa", approximate=False, prior=None)
        self._pm = read_pm(model_path, cfg)
        self._am = read_am(model_path, cfg)
        self._am.eval() if hasattr(self._am, "eval") else None
        phones = [ln.split()[0] for ln in (model_path / "phone.txt").read_text(encoding="utf-8").splitlines() if ln.strip()]
        tok = {p: i + 1 for i, p in enumerate(phones)}  # 0 = blank
        self._token_names = {i: p for p, i in tok.items()}
        for label, options in _UNITS.items():
            units = []
            for opt in options:
                if all(t in tok for t in opt):
                    units.append(tuple(tok[t] for t in opt))
            if not units:
                raise EngineUnavailable(f"model {model} lacks phones for {label}")
            self._register(label, units[0], units[1:])
        self.calibration_id = f"allosaurus-{model}"

    def log_posteriors(self, audio: np.ndarray) -> np.ndarray:
        from allosaurus.audio import Audio

        torch = self._torch
        a = Audio((np.clip(audio, -1, 1) * 32767.0).astype(np.float32), 16000)  # Allosaurus expects int16 scale
        feat = self._pm.compute(a)
        x = torch.from_numpy(np.expand_dims(feat, 0))
        xl = torch.tensor([feat.shape[0]], dtype=torch.int32)
        with torch.no_grad():
            out = self._am(x, xl)[0].numpy().astype(np.float64)
        # log-softmax over the model's output inventory
        m = out.max(axis=1, keepdims=True)
        return out - m - np.log(np.exp(out - m).sum(axis=1, keepdims=True))
