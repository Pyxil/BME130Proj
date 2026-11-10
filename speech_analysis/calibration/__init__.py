"""Score calibration tables.

* ``<engine>.json`` - monotone mapping from GOP posterior to a 0-100 phone
  score, fitted on human expert scores (speechocean762 train split) by
  ``scripts/evaluate_speechocean762.py --fit-calibration``.
* ``dtw.json`` - logistic parameters mapping DTW cost to acoustic similarity,
  produced by ``scripts/calibrate_dtw.py``.

If a file is missing the pipeline falls back to transparent defaults
(score = 100 x posterior) and reports ``calibration: null`` in results.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CAL_DIR = Path(__file__).resolve().parent


@dataclass
class PhoneCalibration:
    data: dict
    source: str

    def score(self, posterior: float, phone: str = "") -> int:
        from .fit import apply

        return int(round(float(apply(self.data, np.array([posterior]), np.array([phone or "?"]))[0])))

    def word_score(self, phone_scores: list[float]) -> float | None:
        """Expected expert word rating (0-100) from calibrated phone scores, if a word curve exists."""
        from .fit import apply_word

        return apply_word(self.data, phone_scores)


@dataclass
class DTWCalibration:
    midpoint: float
    scale: float
    source: str


def load_phone_calibration(engine_id: str | None, override: Path | None = None) -> PhoneCalibration | None:
    path = override or (CAL_DIR / f"{engine_id}.json" if engine_id else None)
    if path is None or not Path(path).exists():
        return None
    data = json.loads(Path(path).read_text())
    if "global" not in data:  # legacy single-curve format on the posterior axis
        xs, ys = data["x_posterior"], data["y_score"]
        lx = [float(np.log(max(x, 1e-4))) for x in xs]
        data = {"axis": "log_posterior", "clip": 1e-4, "global": {"x": lx, "y": ys}, "per_phone": {}}
    return PhoneCalibration(data, data.get("fitted_on", str(path)))


def load_dtw_calibration() -> DTWCalibration | None:
    path = CAL_DIR / "dtw.json"
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    return DTWCalibration(float(d["midpoint"]), float(d["scale"]), d.get("fitted_on", "dtw.json"))
