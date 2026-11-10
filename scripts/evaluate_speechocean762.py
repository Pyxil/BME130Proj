#!/usr/bin/env python3
"""Validate phoneme scoring against human expert scores (speechocean762).

speechocean762 (Zhang et al., Interspeech 2021, CC BY 4.0) contains 5,000
English utterances by 250 non-native speakers (adults and children), each
phone scored 0-2 by five experts.  Get it with::

    git clone --depth 1 https://github.com/jimbozhang/speechocean762 /data/speechocean762

Usage::

    # 1) fit the score calibration on the train split
    python scripts/evaluate_speechocean762.py --data /data/speechocean762 --split train \
        --limit 1500 --fit-calibration speech_analysis/calibration/allosaurus-eng2102.json
    # 2) evaluate on the held-out test split
    python scripts/evaluate_speechocean762.py --data /data/speechocean762 --split test \
        --calibration speech_analysis/calibration/allosaurus-eng2102.json --report docs/validation_results.json

Metrics: Pearson/Spearman correlation between phone posteriors (or calibrated
scores) and mean human phone scores, mispronunciation-detection AUC, and
word/utterance-level correlations.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_ENGINE = None


def _init(model_dir: str, model: str, threads: int) -> None:
    global _ENGINE
    from speech_analysis.phoneme_analysis.engines.allosaurus_engine import AllosaurusEngine

    _ENGINE = AllosaurusEngine(Path(model_dir), model=model, threads=threads)


def _restress(word: str, phones: list[str]) -> list[str]:
    """Use CMUdict stress digits when the phone string matches (corpus stress is unreliable)."""
    from speech_analysis.phoneme_analysis.lexicon import cmudict_pronunciations, strip_stress

    base = tuple(p.rstrip("012") for p in phones)
    for pron in cmudict_pronunciations(word):
        if strip_stress(pron) == base:
            return pron
    return phones


def _process(item):
    import soundfile as sf

    utt_id, wav_path, words = item
    y, sr = sf.read(wav_path, dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    if sr != 16000:
        from speech_analysis.audio_processing.io import resample

        y = resample(y, sr, 16000)
    arpabet, word_idx, human = [], [], []
    for wi, w in enumerate(words):
        phones = _restress(w["text"], w["phones"])
        arpabet += phones
        word_idx += [wi] * len(phones)
        human += list(w["phones-accuracy"])
    try:
        lp = _ENGINE.log_posteriors(y)
        va = _ENGINE._assess_variant(lp, {"id": "utt", "arpabet": arpabet})
    except Exception as exc:  # noqa: BLE001
        return {"utt": utt_id, "error": str(exc)}
    return {
        "utt": utt_id,
        "posterior": [p.posterior for p in va.phones],
        "strict": [p.strict_posterior for p in va.phones],
        "deletion": [p.deletion_prob for p in va.phones],
        "alt_prob": [p.best_alternative_prob for p in va.phones],
        "alt": [p.best_alternative or "DEL" for p in va.phones],
        "human": human,
        "word_idx": word_idx,
        "word_human": [w["accuracy"] for w in words],
        "phones": arpabet,
    }


def _auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """Probability that a random positive scores lower than a random negative (rank-based)."""
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    allv = np.concatenate([pos, neg])
    ranks = allv.argsort().argsort().astype(float) + 1
    r_pos = ranks[: len(pos)].sum()
    u = r_pos - len(pos) * (len(pos) + 1) / 2
    return float(1 - u / (len(pos) * len(neg)))


def _pav(x: np.ndarray, y: np.ndarray, bins: int = 25) -> tuple[list[float], list[float]]:
    """Monotone (isotonic) calibration knots from quantile bins + pool-adjacent-violators."""
    order = np.argsort(x)
    x, y = x[order], y[order]
    edges = np.unique(np.quantile(x, np.linspace(0, 1, bins + 1)))
    xs, ys, ws = [], [], []
    for a, b in zip(edges, edges[1:]):
        m = (x >= a) & (x <= b)
        if m.sum() == 0:
            continue
        xs.append(float(x[m].mean()))
        ys.append(float(y[m].mean()))
        ws.append(float(m.sum()))
    # pool adjacent violators
    blocks = [[xs[i], ys[i], ws[i]] for i in range(len(xs))]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][1] > blocks[i + 1][1]:
            w = blocks[i][2] + blocks[i + 1][2]
            blocks[i] = [
                (blocks[i][0] * blocks[i][2] + blocks[i + 1][0] * blocks[i + 1][2]) / w,
                (blocks[i][1] * blocks[i][2] + blocks[i + 1][1] * blocks[i + 1][2]) / w,
                w,
            ]
            del blocks[i + 1]
            i = max(0, i - 1)
        else:
            i += 1
    return [b[0] for b in blocks], [b[1] for b in blocks]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--split", default="test", choices=["train", "test"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--model-dir", default=str(ROOT / "models"))
    ap.add_argument("--model", default="eng2102")
    ap.add_argument("--fit-calibration", type=Path)
    ap.add_argument("--calibration", type=Path)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--save-raw", type=Path, help="save per-phone arrays (.npz) for analysis")
    ap.add_argument("--fail-under-auc", type=float, help="exit 1 if mispronunciation AUC falls below this (CI guard)")
    args = ap.parse_args()

    scores = json.loads((args.data / "resource" / "scores.json").read_text())
    wav = dict(ln.split("\t") for ln in (args.data / args.split / "wav.scp").read_text().splitlines() if ln.strip())
    ids = sorted(wav)
    if args.limit:
        rng = np.random.default_rng(0)
        ids = sorted(rng.choice(ids, size=min(args.limit, len(ids)), replace=False).tolist())
    items = [(u, str(args.data / wav[u].strip()), scores[u]["words"]) for u in ids]

    t0 = time.time()
    with mp.get_context("spawn").Pool(args.workers, initializer=_init, initargs=(args.model_dir, args.model, 1)) as pool:
        results = pool.map(_process, items, chunksize=8)
    elapsed = time.time() - t0
    ok = [r for r in results if "error" not in r]
    print(f"processed {len(ok)}/{len(results)} utterances in {elapsed:.0f}s")

    post = np.concatenate([r["posterior"] for r in ok])
    strict = np.concatenate([r["strict"] for r in ok])
    human = np.concatenate([r["human"] for r in ok]).astype(float)
    from scipy.stats import pearsonr, spearmanr

    metrics: dict = {"split": args.split, "utterances": len(ok), "phones": int(len(post)), "model": args.model}
    metrics["phone_pcc_posterior"] = round(float(pearsonr(post, human)[0]), 4)
    metrics["phone_pcc_strict_posterior"] = round(float(pearsonr(strict, human)[0]), 4)
    metrics["phone_pcc_log_posterior"] = round(float(pearsonr(np.log(np.clip(post, 1e-4, 1)), human)[0]), 4)
    metrics["phone_spearman"] = round(float(spearmanr(post, human)[0]), 4)
    wrong, right = post[human <= 1.0], post[human >= 2.0]
    metrics["mispronunciation_auc"] = round(_auc(wrong, right), 4)
    metrics["n_mispronounced_phones"] = int(len(wrong))

    # word level: mean phone posterior vs human word accuracy (0-10)
    w_pred, w_human = [], []
    for r in ok:
        wi = np.array(r["word_idx"])
        for k, h in enumerate(r["word_human"]):
            m = wi == k
            if m.any():
                w_pred.append(float(np.mean(np.array(r["posterior"])[m])))
                w_human.append(float(h))
    metrics["word_pcc"] = round(float(pearsonr(w_pred, w_human)[0]), 4)
    # alternative word aggregations (min phone, mean log posterior, soft-min)
    aggs = {"min": [], "mean_log": [], "softmin": []}
    for r in ok:
        wi = np.array(r["word_idx"])
        pp = np.array(r["posterior"])
        for k in range(len(r["word_human"])):
            m = wi == k
            if m.any():
                v = pp[m]
                aggs["min"].append(float(v.min()))
                aggs["mean_log"].append(float(np.mean(np.log(np.clip(v, 1e-4, 1)))))
                aggs["softmin"].append(float(0.5 * v.mean() + 0.5 * v.min()))
    for name, vals in aggs.items():
        metrics[f"word_pcc_{name}"] = round(float(pearsonr(vals, w_human)[0]), 4)

    if args.fit_calibration:
        xs, ys = _pav(post, human / 2.0 * 100.0)
        cal = {"engine": f"allosaurus-{args.model}", "x_posterior": xs, "y_score": ys,
               "fitted_on": f"speechocean762 {args.split} ({len(ok)} utterances, {len(post)} phones)",
               "target": "mean expert phone accuracy (0-2) scaled to 0-100"}
        args.fit_calibration.parent.mkdir(parents=True, exist_ok=True)
        args.fit_calibration.write_text(json.dumps(cal, indent=2))
        print(f"wrote calibration with {len(xs)} knots to {args.fit_calibration}")
    if args.calibration:
        cal = json.loads(args.calibration.read_text())
        cal_scores = np.interp(post, cal["x_posterior"], cal["y_score"])
        metrics["phone_pcc_calibrated"] = round(float(pearsonr(cal_scores, human)[0]), 4)
        metrics["phone_mae_calibrated_0_100"] = round(float(np.mean(np.abs(cal_scores - human / 2 * 100))), 2)
    for k, v in metrics.items():
        print(f"{k:32s} {v}")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(metrics, indent=2))
    if args.fail_under_auc is not None and metrics["mispronunciation_auc"] < args.fail_under_auc:
        print(f"FAIL: mispronunciation AUC {metrics['mispronunciation_auc']} < {args.fail_under_auc}", file=sys.stderr)
        return 1
    if args.save_raw:
        np.savez_compressed(args.save_raw, posterior=post, strict=strict, human=human,
                            deletion=np.concatenate([r["deletion"] for r in ok]),
                            alt_prob=np.concatenate([r["alt_prob"] for r in ok]),
                            alt=np.array(sum([r["alt"] for r in ok], [])),
                            word_idx=np.concatenate([np.array(r["word_idx"]) + 1000 * i for i, r in enumerate(ok)]),
                            word_human=np.array(sum([r["word_human"] for r in ok], [])),
                            phones=np.array(sum([r["phones"] for r in ok], [])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
