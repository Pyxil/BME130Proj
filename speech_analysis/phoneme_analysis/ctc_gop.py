"""CTC-based Goodness of Pronunciation (GOP).

This module is pure NumPy so the scoring mathematics can be unit-tested
without any neural network installed.  Engines that produce frame-level CTC
log posteriors (Allosaurus, wav2vec2, ...) feed them in here.

Method
------
For a canonical phone sequence ``c = c_1 .. c_N`` and CTC log posteriors ``X``
we compute, for every position ``i``, the probability that the speaker
produced ``c_i`` *rather than any other phone or nothing*, holding the rest of
the canonical sequence fixed::

                        P_ctc(c | X)
    P(c_i | X) = ---------------------------------------------
                 P_ctc(c | X) + sum_q P_ctc(c[i -> q] | X) + P_ctc(c[i -> {}] | X)

``P_ctc`` is the CTC sequence likelihood (forward algorithm, summing over all
alignments).  ``c[i -> q]`` replaces phone ``i`` by ``q``; ``c[i -> {}]`` deletes it.

This is the substitution-aware, alignment-free GOP formulation described in
Cao et al., "A Framework for Phoneme-Level Pronunciation Assessment Using CTC"
(Interspeech 2024), itself a CTC analogue of the log-posterior-ratio GOP of
Witt & Young (2000).  Unlike scoring the forced alignment alone, it explicitly
asks "would a different sound explain the audio better?", so a fluent but
wrong sound receives a low score.

Besides the posterior we return the most likely competing phone (for
diagnostics such as "/r/ may have sounded like /w/") and the deletion
probability.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

NEG_INF = -np.inf


def _logsumexp(values: Iterable[float]) -> float:
    arr = np.asarray(list(values), dtype=np.float64)
    if arr.size == 0:
        return NEG_INF
    m = np.max(arr)
    if not np.isfinite(m):
        return float(m)
    return float(m + np.log(np.sum(np.exp(arr - m))))


def ctc_log_likelihoods(
    log_probs: np.ndarray, sequences: Sequence[Sequence[int]], blank: int
) -> np.ndarray:
    """Batched CTC forward algorithm.

    Args:
        log_probs: ``(T, V)`` array of per-frame log posteriors (log-softmax).
        sequences: label sequences (token ids, no blanks). May differ in length.
        blank: id of the CTC blank token.

    Returns:
        ``(B,)`` array with ``log P(sequence | X)`` (``-inf`` if impossible).
    """
    log_probs = np.asarray(log_probs, dtype=np.float64)
    T = log_probs.shape[0]
    B = len(sequences)
    if B == 0:
        return np.zeros(0)
    if T == 0:
        return np.full(B, NEG_INF)

    lens = np.array([len(s) for s in sequences], dtype=np.int64)
    S = 2 * lens + 1
    s_max = int(S.max())
    ext = np.full((B, s_max), blank, dtype=np.int64)
    for b, seq in enumerate(sequences):
        if len(seq):
            ext[b, 1 : 2 * len(seq) : 2] = np.asarray(seq, dtype=np.int64)

    # Skip transition s-2 -> s is allowed onto a non-blank label that differs
    # from the label two states back (standard CTC topology).
    skip = np.zeros((B, s_max), dtype=bool)
    if s_max > 2:
        skip[:, 2:] = (ext[:, 2:] != blank) & (ext[:, 2:] != ext[:, :-2])
    valid = np.arange(s_max)[None, :] < S[:, None]

    alpha = np.full((B, s_max), NEG_INF)
    emit0 = log_probs[0][ext]
    alpha[:, 0] = emit0[:, 0]
    if s_max > 1:
        alpha[:, 1] = np.where(lens > 0, emit0[:, 1], NEG_INF)
    alpha[~valid] = NEG_INF

    shifted1 = np.full((B, s_max), NEG_INF)
    shifted2 = np.full((B, s_max), NEG_INF)
    with np.errstate(invalid="ignore"):
        for t in range(1, T):
            shifted1[:, 1:] = alpha[:, :-1]
            if s_max > 2:
                shifted2[:, 2:] = np.where(skip[:, 2:], alpha[:, :-2], NEG_INF)
            alpha = np.logaddexp(np.logaddexp(alpha, shifted1), shifted2) + log_probs[t][ext]
            alpha[~valid] = NEG_INF

    idx = np.arange(B)
    last = alpha[idx, S - 1]
    second = np.where(lens > 0, alpha[idx, np.maximum(S - 2, 0)], NEG_INF)
    return np.logaddexp(last, second)


@dataclass
class AlignedToken:
    """A token's span in a CTC Viterbi alignment (frames, inclusive start, exclusive end)."""

    position: int
    token: int
    peak_start: int
    peak_end: int
    seg_start: int
    seg_end: int


def ctc_viterbi_align(
    log_probs: np.ndarray, sequence: Sequence[int], blank: int
) -> tuple[float, list[AlignedToken]]:
    """Best single CTC path for ``sequence`` (forced alignment).

    ``peak_*`` covers frames emitting the token itself (CTC outputs are peaky,
    so this is usually short).  ``seg_*`` extends each token over neighbouring
    blank frames, splitting blank runs halfway between tokens, to give an
    approximate phone segment usable for timing and region mapping.  These
    segments are approximations, not phonetically exact boundaries.
    """
    log_probs = np.asarray(log_probs, dtype=np.float64)
    T = log_probs.shape[0]
    U = len(sequence)
    if U == 0 or T == 0:
        return NEG_INF, []
    S = 2 * U + 1
    ext = np.full(S, blank, dtype=np.int64)
    ext[1::2] = np.asarray(sequence, dtype=np.int64)
    skip = np.zeros(S, dtype=bool)
    skip[2:] = (ext[2:] != blank) & (ext[2:] != ext[:-2])

    delta = np.full((T, S), NEG_INF)
    back = np.zeros((T, S), dtype=np.int8)  # 0 stay, 1 from s-1, 2 from s-2
    delta[0, 0] = log_probs[0, ext[0]]
    delta[0, 1] = log_probs[0, ext[1]]
    for t in range(1, T):
        prev = delta[t - 1]
        cand0 = prev
        cand1 = np.full(S, NEG_INF)
        cand1[1:] = prev[:-1]
        cand2 = np.full(S, NEG_INF)
        cand2[2:] = np.where(skip[2:], prev[:-2], NEG_INF)
        stacked = np.stack([cand0, cand1, cand2])
        choice = np.argmax(stacked, axis=0)
        delta[t] = stacked[choice, np.arange(S)] + log_probs[t, ext]
        back[t] = choice

    end_candidates = [S - 1, S - 2]
    end_state = max(end_candidates, key=lambda s: delta[T - 1, s])
    score = float(delta[T - 1, end_state])
    if not np.isfinite(score):
        return NEG_INF, []

    states = np.zeros(T, dtype=np.int64)
    s = end_state
    for t in range(T - 1, -1, -1):
        states[t] = s
        s -= int(back[t, s])

    peaks: list[list[int]] = [[] for _ in range(U)]
    for t, st in enumerate(states):
        if st % 2 == 1:
            peaks[st // 2].append(t)

    tokens: list[AlignedToken] = []
    for u in range(U):
        frames = peaks[u]
        tokens.append(
            AlignedToken(
                position=u,
                token=int(sequence[u]),
                peak_start=frames[0],
                peak_end=frames[-1] + 1,
                seg_start=frames[0],
                seg_end=frames[-1] + 1,
            )
        )
    # Split blank runs halfway between consecutive tokens.
    for u in range(U - 1):
        gap_start, gap_end = tokens[u].peak_end, tokens[u + 1].peak_start
        mid = gap_start + (gap_end - gap_start) // 2
        tokens[u].seg_end = mid
        tokens[u + 1].seg_start = mid
    return score, tokens


def greedy_decode(log_probs: np.ndarray, blank: int) -> list[tuple[int, int, int]]:
    """Best-path (greedy) CTC decoding: list of ``(token, start_frame, end_frame)``."""
    best = np.argmax(np.asarray(log_probs), axis=1)
    out: list[tuple[int, int, int]] = []
    prev = blank
    for t, tok in enumerate(best):
        tok = int(tok)
        if tok != blank and tok != prev:
            out.append((tok, t, t + 1))
        elif tok != blank and tok == prev and out:
            out[-1] = (out[-1][0], out[-1][1], t + 1)
        prev = tok
    return out


@dataclass
class PositionGop:
    """GOP outcome for one canonical position."""

    position: int
    token: object  # canonical unit (token id or tuple of ids)
    log_posterior: float  # log P(canonical unit at i)
    accepted_log_posterior: float  # including accepted variants (accent/allophones)
    best_alternative: object | None  # most likely competing unit (None = deletion)
    best_alternative_log_posterior: float
    deletion_log_posterior: float
    best_accepted_variant: object | None = None
    distribution: dict = field(default_factory=dict)

    @property
    def posterior(self) -> float:
        return float(np.exp(self.log_posterior))

    @property
    def accepted_posterior(self) -> float:
        return float(np.exp(self.accepted_log_posterior))


@dataclass
class GopResult:
    canonical_log_likelihood: float
    frames: int
    positions: list[PositionGop]


Unit = "int | tuple[int, ...]"


def _as_tuple(u) -> tuple[int, ...]:
    return tuple(int(x) for x in u) if isinstance(u, (tuple, list)) else (int(u),)


def ctc_gop(
    log_probs: np.ndarray,
    canonical: Sequence,
    candidates: Sequence,
    blank: int,
    accepted: Mapping[int, Iterable] | None = None,
    include_deletion: bool = True,
    keep_distribution: bool = False,
    backend: str = "auto",
) -> GopResult:
    """Substitution/deletion-aware GOP for every canonical position.

    Elements of ``canonical`` and ``candidates`` are *units*: either a single
    token id or a tuple of token ids (e.g. a diphthong that the recogniser
    writes as two symbols).  Substitution replaces a whole unit.

    Args:
        log_probs: ``(T, V)`` CTC log posteriors.
        canonical: canonical units.
        candidates: units considered as substitutes (typically the whole
            phone inventory of the language).
        blank: blank token id.
        accepted: optional ``{position: units}`` treated as *correct*
            realisations (allophones, accepted accent variants).  They are added
            to the numerator of the accepted posterior.
        include_deletion: also consider deleting the unit.
        keep_distribution: include the full per-position distribution.
        backend: ``"numpy"``, ``"torch"`` or ``"auto"`` (torch when installed
            and the batch is large).
    """
    canon_t = [_as_tuple(c) for c in canonical]
    cand_objs = list(candidates)
    cand_t = [_as_tuple(c) for c in cand_objs]
    U = len(canon_t)
    accepted_t = {int(k): {_as_tuple(t) for t in v} for k, v in (accepted or {}).items()}

    def flat(units: list[tuple[int, ...]]) -> list[int]:
        return [tok for u in units for tok in u]

    seqs: list[list[int]] = [flat(canon_t)]
    index: list[tuple[int, int | None]] = []  # (position, candidate index or None=deletion)
    for i in range(U):
        for ci, q in enumerate(cand_t):
            if q == canon_t[i] or blank in q:
                continue
            seqs.append(flat(canon_t[:i] + [q] + canon_t[i + 1 :]))
            index.append((i, ci))
        if include_deletion:
            seqs.append(flat(canon_t[:i] + canon_t[i + 1 :]))
            index.append((i, None))

    ll = sequence_log_likelihoods(log_probs, seqs, blank, backend=backend)
    ll0 = float(ll[0])

    by_pos: dict[int, list[tuple[int | None, float]]] = {i: [] for i in range(U)}
    for k, (pos, ci) in enumerate(index):
        by_pos[pos].append((ci, float(ll[k + 1])))

    def obj(ci):
        return None if ci is None else cand_objs[ci]

    positions: list[PositionGop] = []
    for i in range(U):
        alts = by_pos[i]
        denom = _logsumexp([ll0] + [v for _, v in alts])
        if not np.isfinite(denom):
            positions.append(PositionGop(i, canonical[i], NEG_INF, NEG_INF, None, NEG_INF, NEG_INF))
            continue
        ok = accepted_t.get(i, set())
        is_ok = [ci is not None and cand_t[ci] in ok for ci, _ in alts]
        ok_vals = [v for (ci, v), good in zip(alts, is_ok) if good]
        accepted_lp = _logsumexp([ll0] + ok_vals) - denom
        best_ok = None
        if ok_vals:
            bci, bv = max(((ci, v) for (ci, v), good in zip(alts, is_ok) if good), key=lambda x: x[1])
            if bv > ll0:
                best_ok = obj(bci)
        competitors = [(ci, v) for (ci, v), good in zip(alts, is_ok) if not good]
        if competitors:
            bci, bv = max(competitors, key=lambda x: x[1])
            best_alt, best_alt_lp = obj(bci), bv - denom
        else:
            best_alt, best_alt_lp = None, NEG_INF
        del_vals = [v for ci, v in alts if ci is None]
        del_lp = (del_vals[0] - denom) if del_vals else NEG_INF
        dist: dict = {}
        if keep_distribution:
            dist["canonical"] = ll0 - denom
            for ci, v in alts:
                dist[ci] = v - denom
        positions.append(
            PositionGop(
                position=i,
                token=canonical[i],
                log_posterior=ll0 - denom,
                accepted_log_posterior=accepted_lp,
                best_alternative=best_alt,
                best_alternative_log_posterior=best_alt_lp,
                deletion_log_posterior=del_lp,
                best_accepted_variant=best_ok,
                distribution=dist,
            )
        )
    return GopResult(canonical_log_likelihood=ll0, frames=int(np.asarray(log_probs).shape[0]), positions=positions)


def sequence_log_likelihoods(
    log_probs: np.ndarray, sequences: Sequence[Sequence[int]], blank: int, backend: str = "auto"
) -> np.ndarray:
    """CTC log-likelihoods for many label sequences (NumPy or PyTorch backend).

    The PyTorch path (``torch.nn.functional.ctc_loss``) is used for large
    batches such as sentence-level evaluation; results are identical up to
    floating point error (see tests).
    """
    use_torch = backend == "torch"
    if backend == "auto" and len(sequences) * np.asarray(log_probs).shape[0] > 200_000:
        try:
            import torch  # noqa: F401

            use_torch = True
        except ImportError:
            use_torch = False
    if not use_torch:
        return ctc_log_likelihoods(log_probs, sequences, blank)
    import torch
    import torch.nn.functional as F

    lp = torch.as_tensor(np.asarray(log_probs, dtype=np.float32))
    T, V = lp.shape
    B = len(sequences)
    lens = [len(s) for s in sequences]
    max_len = max(1, max(lens))
    targets = torch.full((B, max_len), 1 if blank == 0 else 0, dtype=torch.long)
    for b, s in enumerate(sequences):
        if len(s):
            targets[b, : len(s)] = torch.as_tensor(list(s), dtype=torch.long)
    out = np.empty(B, dtype=np.float64)
    chunk = max(1, int(4_000_000 // max(1, T * V)))
    for start in range(0, B, chunk):
        end = min(B, start + chunk)
        n = end - start
        inp = lp.unsqueeze(1).expand(T, n, V).contiguous()
        nll = F.ctc_loss(
            inp, targets[start:end], torch.full((n,), T, dtype=torch.long),
            torch.as_tensor(lens[start:end], dtype=torch.long), blank=blank, reduction="none", zero_infinity=False,
        )
        out[start:end] = -nll.double().numpy()
    out[~np.isfinite(out)] = NEG_INF
    return out
