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
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "global" not in data:  # legacy single-curve format on the posterior axis
        xs, ys = data["x_posterior"], data["y_score"]
        lx = [float(np.log(max(x, 1e-4))) for x in xs]
        data = {"axis": "log_posterior", "clip": 1e-4, "global": {"x": lx, "y": ys}, "per_phone": {}}
    return PhoneCalibration(data, data.get("fitted_on", str(path)))


@dataclass
class SignalCalibration:
    """Maps signal-comparison measures to 0-100 scores (see ``scripts/calibrate_signal.py``).

    * spectral distance d -> 100 / (1 + exp((d - midpoint) / scale)), for the whole word and for parts;
    * loudness-envelope correlation r -> linear from ``loudness_low`` (0) to ``loudness_high`` (100);
    * pitch-contour RMS difference (semitones) -> linear from ``pitch_good`` (100) to ``pitch_bad`` (0);
    * minimal-pair contrast c -> probability of the mistake 1 / (1 + exp(-(c - mistake_midpoint) / mistake_scale)).
    """

    distance_midpoint: float = 0.80
    distance_scale: float = 0.06
    part_midpoint: float = 0.85
    part_scale: float = 0.07
    loudness_low: float = 0.60
    loudness_high: float = 0.95
    pitch_good: float = 5.0
    pitch_bad: float = 14.0
    mistake_midpoint: float = 0.05  # minimal-pair contrast with a 50% chance of the mistake
    mistake_scale: float = 0.02
    source: str = "defaults (uncalibrated)"
    validation: dict | None = None


def load_signal_calibration(path: Path | None = None) -> SignalCalibration:
    path = path or CAL_DIR / "signal.json"
    if not path.exists():
        return SignalCalibration()
    d = json.loads(path.read_text(encoding="utf-8"))
    return SignalCalibration(
        distance_midpoint=d["distance"]["midpoint"], distance_scale=d["distance"]["scale"],
        part_midpoint=d["part"]["midpoint"], part_scale=d["part"]["scale"],
        loudness_low=d["loudness"]["low"], loudness_high=d["loudness"]["high"],
        pitch_good=d["pitch"]["good"], pitch_bad=d["pitch"]["bad"],
        mistake_midpoint=d["mistake"]["midpoint"], mistake_scale=d["mistake"]["scale"],
        source=d.get("fitted_on", str(path)), validation=d.get("validation"),
    )


def load_dtw_calibration() -> DTWCalibration | None:
    path = CAL_DIR / "dtw.json"
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    return DTWCalibration(float(d["midpoint"]), float(d["scale"]), d.get("fitted_on", "dtw.json"))
