"""Fit monotone phone-score calibration from (posterior, human score) pairs.

Model: for phone ``p`` with log posterior ``lp`` the calibrated score is

    s(p, lp) = w_p * f_p(lp) + (1 - w_p) * f_global(lp),   w_p = e_p / (e_p + k)

where ``f`` are isotonic (pool-adjacent-violators) fits of the mean expert
score (scaled to 0-100) on quantile bins of ``lp``, ``e_p`` is the number of
expert-judged errors for that phone and ``k`` a shrinkage constant.  Phones
with little data therefore fall back to the global curve.
"""

from __future__ import annotations

import numpy as np

CLIP = 1e-4


def isotonic_bins(x: np.ndarray, y: np.ndarray, bins: int) -> tuple[list[float], list[float]]:
    order = np.argsort(x)
    x, y = x[order], y[order]
    edges = np.unique(np.quantile(x, np.linspace(0, 1, bins + 1)))
    blocks: list[list[float]] = []
    for a, b in zip(edges, edges[1:]):
        m = (x >= a) & (x <= b)
        if m.sum():
            blocks.append([float(x[m].mean()), float(y[m].mean()), float(m.sum())])
    i = 0
    while i < len(blocks) - 1:  # pool adjacent violators
        if blocks[i][1] > blocks[i + 1][1]:
            w = blocks[i][2] + blocks[i + 1][2]
            blocks[i] = [(blocks[i][0] * blocks[i][2] + blocks[i + 1][0] * blocks[i + 1][2]) / w,
                         (blocks[i][1] * blocks[i][2] + blocks[i + 1][1] * blocks[i + 1][2]) / w, w]
            del blocks[i + 1]
            i = max(0, i - 1)
        else:
            i += 1
    return [b[0] for b in blocks], [b[1] for b in blocks]


def fit(posterior: np.ndarray, human_0_2: np.ndarray, phones: np.ndarray, shrinkage: float = 40.0,
        global_bins: int = 30, phone_bins: int = 10, min_phone_n: int = 150) -> dict:
    lp = np.log(np.clip(posterior, CLIP, 1.0))
    target = human_0_2 / 2.0 * 100.0
    base = np.array([str(p).rstrip("012") for p in phones])
    gx, gy = isotonic_bins(lp, target, global_bins)
    per_phone = {}
    for p in sorted(set(base)):
        m = base == p
        n, n_wrong = int(m.sum()), int((m & (human_0_2 <= 1.0)).sum())
        if n < min_phone_n:
            continue
        px, py = isotonic_bins(lp[m], target[m], phone_bins)
        per_phone[p] = {"x": px, "y": py, "weight": round(n_wrong / (n_wrong + shrinkage), 4), "n": n, "n_wrong": n_wrong}
    return {"axis": "log_posterior", "clip": CLIP, "global": {"x": gx, "y": gy}, "per_phone": per_phone}


def apply(cal: dict, posterior: np.ndarray, phones: np.ndarray) -> np.ndarray:
    lp = np.log(np.clip(posterior, cal.get("clip", CLIP), 1.0))
    g = np.interp(lp, cal["global"]["x"], cal["global"]["y"])
    out = g.copy()
    base = np.array([str(p).rstrip("012") for p in phones])
    for p, c in cal.get("per_phone", {}).items():
        m = base == p
        if m.any():
            out[m] = c["weight"] * np.interp(lp[m], c["x"], c["y"]) + (1 - c["weight"]) * g[m]
    return np.clip(out, 0, 100)


WORD_THRESHOLD = 85.0
WORD_PENALTY = 1.0


def word_feature(phone_scores: np.ndarray, threshold: float = WORD_THRESHOLD, penalty: float = WORD_PENALTY) -> float:
    """Mean calibrated phone score minus the summed shortfall of each phone below ``threshold``.

    Experts judge a word largely by its worst sounds; on speechocean762 this
    feature correlates better with expert word scores than the mean or min.
    """
    s = np.asarray(phone_scores, dtype=float)
    return float(s.mean() - penalty * np.clip(threshold - s, 0, None).sum())


def fit_word(cal: dict, posterior: np.ndarray, phones: np.ndarray, word_idx: np.ndarray,
             word_human_0_10: np.ndarray, bins: int = 30) -> dict:
    scores = apply(cal, posterior, phones)
    uniq, inv = np.unique(word_idx, return_inverse=True)
    feats = np.array([word_feature(scores[inv == k]) for k in range(len(uniq))])
    xs, ys = isotonic_bins(feats, np.asarray(word_human_0_10, dtype=float) * 10.0, bins)
    return {"feature": "mean_minus_deficit", "threshold": WORD_THRESHOLD, "penalty": WORD_PENALTY, "x": xs, "y": ys}


def apply_word(cal: dict, phone_scores: list[float]) -> float | None:
    w = cal.get("word")
    if not w or not phone_scores:
        return None
    f = word_feature(np.array(phone_scores), w.get("threshold", WORD_THRESHOLD), w.get("penalty", WORD_PENALTY))
    return float(np.clip(np.interp(f, w["x"], w["y"]), 0, 100))
