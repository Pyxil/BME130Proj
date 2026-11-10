"""Shared implementation for engines that output CTC phone posteriors."""

from __future__ import annotations

import threading
from abc import abstractmethod

import numpy as np

from ..ctc_gop import ctc_gop, ctc_viterbi_align, greedy_decode, sequence_log_likelihoods
from ..variation import CANDIDATE_LABELS, accepted_alternatives, label_for
from .base import EngineOutput, PhoneAssessment, PhonemeEngine, VariantAssessment


def _edit_distance(a: list, b: list) -> int:
    dp = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, dp[0] = dp[0], i
        for j, y in enumerate(b, 1):
            cur = dp[j]
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + (x != y))
            prev = cur
    return dp[-1]


class CTCPhonemeEngine(PhonemeEngine):
    """Subclasses provide ``log_posteriors`` and the label->token-unit mapping."""

    blank: int = 0
    frame_rate: float = 100.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._units: dict[str, tuple[int, ...]] = {}
        self._alt_units: dict[str, list[tuple[int, ...]]] = {}
        self._token_names: dict[int, str] = {}

    # ------------------------------------------------------------ subclass API
    @abstractmethod
    def log_posteriors(self, audio: np.ndarray) -> np.ndarray:
        """(T, V) log posteriors for 16 kHz float32 audio."""

    def _register(self, label: str, unit: tuple[int, ...], alternates: list[tuple[int, ...]] = ()) -> None:
        self._units[label] = unit
        self._alt_units[label] = [u for u in alternates if u != unit]

    # ----------------------------------------------------------------- helpers
    def unit(self, label: str) -> tuple[int, ...]:
        return self._units[label]

    def units_for(self, arpabet: list[str]) -> list[tuple[int, ...]]:
        return [self._units[label_for(p)] for p in arpabet]

    def _decoded_ipa(self, lp: np.ndarray) -> list[str]:
        toks = [self._token_names.get(t, "?") for t, _, _ in greedy_decode(lp, self.blank)]
        merged: list[str] = []
        glide_pairs = {("a", "j"): "aɪ", ("e", "j"): "eɪ", ("o", "w"): "oʊ", ("a", "w"): "aʊ", ("ɔ", "j"): "ɔɪ",
                       ("o", "j"): "ɔɪ", ("a", "ɪ"): "aɪ", ("e", "ɪ"): "eɪ", ("o", "ʊ"): "oʊ", ("a", "ʊ"): "aʊ"}
        i = 0
        while i < len(toks):
            if i + 1 < len(toks) and (toks[i], toks[i + 1]) in glide_pairs:
                merged.append(glide_pairs[(toks[i], toks[i + 1])])
                i += 2
            else:
                merged.append({"ɹ̩": "ɜr", "ɹ": "r", "t͡ʃ": "tʃ", "d͡ʒ": "dʒ"}.get(toks[i], toks[i]))
                i += 1
        return merged

    def _assess_variant(self, lp: np.ndarray, variant: dict) -> VariantAssessment:
        arpabet = list(variant["arpabet"])
        canonical = self.units_for(arpabet)
        cand_labels = CANDIDATE_LABELS
        cand_units = [self._units[c] for c in cand_labels]
        # accepted realisations: context rules + tokenisation alternates of the same phone
        accepted: dict[int, list[tuple[int, ...]]] = {}
        extra_cands: list[tuple[int, ...]] = []
        extra_labels: list[str] = []
        for i, p in enumerate(arpabet):
            lab = label_for(p)
            acc = [self._units[a] for a in accepted_alternatives(arpabet, i)]
            for alt in self._alt_units.get(lab, []):
                acc.append(alt)
                if alt not in cand_units and alt not in extra_cands:
                    extra_cands.append(alt)
                    extra_labels.append(lab)
            if acc:
                accepted[i] = acc
        all_units = cand_units + extra_cands
        all_labels = cand_labels + extra_labels
        res = ctc_gop(lp, canonical, all_units, self.blank, accepted=accepted)
        _, segs = ctc_viterbi_align(lp, [t for u in canonical for t in u], self.blank)
        # map token segments back to unit (phone) spans
        spans: list[tuple[float, float] | None] = []
        k = 0
        for u in canonical:
            if segs and k + len(u) - 1 < len(segs):
                spans.append((segs[k].seg_start / self.frame_rate, segs[k + len(u) - 1].seg_end / self.frame_rate))
            else:
                spans.append(None)
            k += len(u)
        unit_label = {u: lab for u, lab in zip(all_units, all_labels)}
        phones: list[PhoneAssessment] = []
        for pos in res.positions:
            alt = pos.best_alternative
            acc_var = pos.best_accepted_variant
            span = spans[pos.position]
            phones.append(
                PhoneAssessment(
                    index=pos.position,
                    arpabet=arpabet[pos.position],
                    posterior=float(np.exp(pos.accepted_log_posterior)),
                    strict_posterior=float(np.exp(pos.log_posterior)),
                    best_alternative=None if alt is None else unit_label.get(tuple(alt), "?"),
                    best_alternative_prob=float(np.exp(pos.best_alternative_log_posterior)),
                    deletion_prob=float(np.exp(pos.deletion_log_posterior)),
                    accepted_variant=None if acc_var is None else unit_label.get(tuple(acc_var)),
                    start_s=None if span is None else round(span[0], 3),
                    end_s=None if span is None else round(span[1], 3),
                )
            )
        return VariantAssessment(variant["id"], arpabet, res.canonical_log_likelihood, phones)

    # ------------------------------------------------------------------ public
    def assess(self, audio, variants, vocabulary=None, target_word=None) -> EngineOutput:
        with self._lock:
            lp = self.log_posteriors(audio)
        assessed = [self._assess_variant(lp, v) for v in variants]
        # Best variant = the pronunciation that best explains the audio (accent tolerance).
        best = max(assessed, key=lambda v: (v.log_likelihood, np.mean([p.posterior for p in v.phones])))
        decoded = self._decoded_ipa(lp)

        out = EngineOutput(
            engine=self.name, model=self.model, best=best, variants=assessed, decoded_ipa=decoded,
            frames=int(lp.shape[0]), frame_rate=self.frame_rate, posteriorgram=np.exp(lp),
        )
        # phoneme error rate of the free decoding against the best variant
        ref_tokens = [t for u in self.units_for(best.arpabet) for t in u]
        hyp_tokens = [t for t, _, _ in greedy_decode(lp, self.blank)]
        out.phoneme_error_rate = round(_edit_distance(ref_tokens, hyp_tokens) / max(1, len(ref_tokens)), 3)

        # Closed-vocabulary word recognition: which practice word's pronunciation
        # has the highest CTC likelihood?  (Supplementary signal only.)
        if vocabulary:
            seqs, owners = [], []
            for entry in vocabulary:
                for v in entry["variants"]:
                    try:
                        seqs.append([t for u in self.units_for(v["arpabet"]) for t in u])
                        owners.append(entry["word"])
                    except KeyError:
                        continue
            if seqs:
                ll = sequence_log_likelihoods(lp, seqs, self.blank)
                order = np.argsort(-ll)
                top_word = owners[int(order[0])]
                out.recognized_word = top_word
                if target_word is not None:
                    out.recognized_matches_target = top_word.lower() == target_word.lower()
                    tgt = max((ll[i] for i, w in enumerate(owners) if w.lower() == target_word.lower()), default=-np.inf)
                    other = max((ll[i] for i, w in enumerate(owners) if w.lower() != target_word.lower()), default=-np.inf)
                    if np.isfinite(tgt) and np.isfinite(other):
                        out.recognition_margin = float(tgt - other)
        return out
