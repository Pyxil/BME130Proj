#!/usr/bin/env python3
"""Fit per-phone score calibration from arrays saved by evaluate_speechocean762.py.

    python scripts/evaluate_speechocean762.py --data D --split train --save-raw train.npz
    python scripts/evaluate_speechocean762.py --data D --split test  --save-raw test.npz
    python scripts/fit_calibration.py --train train.npz --test test.npz \
        --out speech_analysis/calibration/allosaurus-eng2102.json --report docs/validation_results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import pearsonr, spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from speech_analysis.calibration import fit as calfit  # noqa: E402


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    allv = np.concatenate([pos, neg])
    ranks = allv.argsort().argsort().astype(float) + 1
    u = ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2
    return float(1 - u / (len(pos) * len(neg)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=Path, required=True)
    ap.add_argument("--test", type=Path)
    ap.add_argument("--engine", default="allosaurus-eng2102")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()

    tr = np.load(args.train)
    cal = calfit.fit(tr["posterior"], tr["human"], tr["phones"])
    if "word_idx" in tr.files:
        cal["word"] = calfit.fit_word(cal, tr["posterior"], tr["phones"], tr["word_idx"], tr["word_human"])
    cal.update({
        "engine": args.engine,
        "fitted_on": f"speechocean762 train ({len(tr['posterior'])} phones)",
        "target": "mean expert phone accuracy (0-2) scaled to 0-100 (expected expert rating)",
    })
    args.out.write_text(json.dumps(cal, indent=1))
    print(f"wrote {args.out} ({len(cal['per_phone'])} phone-specific curves)")

    if args.test:
        te = np.load(args.test)
        post, human, phones = te["posterior"], te["human"], te["phones"]
        cal_scores = calfit.apply(cal, post, phones)
        glob_scores = np.interp(np.log(np.clip(post, 1e-4, 1)), cal["global"]["x"], cal["global"]["y"])
        report = {
            "dataset": "speechocean762 test split (held out)",
            "engine": args.engine,
            "phones": int(len(post)),
            "phone_pcc_raw_posterior": round(float(pearsonr(post, human)[0]), 4),
            "phone_pcc_log_posterior": round(float(pearsonr(np.log(np.clip(post, 1e-4, 1)), human)[0]), 4),
            "phone_pcc_calibrated_global": round(float(pearsonr(glob_scores, human)[0]), 4),
            "phone_pcc_calibrated_per_phone": round(float(pearsonr(cal_scores, human)[0]), 4),
            "phone_spearman_calibrated": round(float(spearmanr(cal_scores, human)[0]), 4),
            "phone_mae_calibrated_0_100": round(float(np.mean(np.abs(cal_scores - human / 2 * 100))), 2),
            "mispronunciation_auc_calibrated": round(auc(cal_scores[human <= 1.0], cal_scores[human >= 2.0]), 4),
            "n_mispronounced": int((human <= 1.0).sum()),
        }
        # precision of the "poor" (<70) and "fair" (<85) bands on the test set
        for thr in (70, 85):
            m = cal_scores < thr
            report[f"p_expert_wrong_given_score_below_{thr}"] = round(float((human[m] <= 1.0).mean()), 3) if m.any() else None
            report[f"fraction_of_phones_below_{thr}"] = round(float(m.mean()), 4)
            report[f"recall_of_expert_errors_below_{thr}"] = round(float((cal_scores[human <= 1.0] < thr).mean()), 3)
        if "word" in cal and "word_idx" in te.files:
            uniq, inv = np.unique(te["word_idx"], return_inverse=True)
            ws = np.array([calfit.apply_word(cal, cal_scores[inv == k].tolist()) for k in range(len(uniq))])
            wh = np.array(te["word_human"], dtype=float) * 10
            report["word_pcc_calibrated"] = round(float(pearsonr(ws, wh)[0]), 4)
            report["word_mae_calibrated_0_100"] = round(float(np.mean(np.abs(ws - wh))), 2)
            report["words"] = int(len(uniq))
            bad = wh <= 60
            report["word_auc_mispronounced"] = round(auc(ws[bad], ws[wh >= 100]), 4)
        for k, v in report.items():
            print(f"{k:45s} {v}")
        if args.report:
            existing = json.loads(args.report.read_text()) if args.report.exists() else {}
            existing["calibrated"] = report
            args.report.write_text(json.dumps(existing, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
