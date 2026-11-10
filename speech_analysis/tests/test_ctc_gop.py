"""Deterministic tests for the CTC GOP mathematics (no neural model needed)."""

import itertools

import numpy as np
import pytest

from speech_analysis.phoneme_analysis.ctc_gop import (
    ctc_gop,
    ctc_log_likelihoods,
    ctc_viterbi_align,
    greedy_decode,
)

BLANK = 0


def _collapse(path):
    out, prev = [], None
    for p in path:
        if p != prev and p != BLANK:
            out.append(p)
        prev = p
    return out


def _brute_force(log_probs, seq):
    T, V = log_probs.shape
    total = 0.0
    for path in itertools.product(range(V), repeat=T):
        if _collapse(path) == list(seq):
            total += np.exp(sum(log_probs[t, p] for t, p in enumerate(path)))
    return np.log(total) if total > 0 else -np.inf


def _random_log_probs(T, V, seed):
    rng = np.random.default_rng(seed)
    logits = rng.normal(size=(T, V))
    return logits - np.log(np.exp(logits).sum(axis=1, keepdims=True))


@pytest.mark.parametrize("seq", [[1], [1, 2], [1, 1], [2, 1, 2], [], [3, 3, 3]])
def test_forward_matches_brute_force(seq):
    lp = _random_log_probs(T=6, V=4, seed=len(seq) + 7)
    expected = _brute_force(lp, seq)
    got = ctc_log_likelihoods(lp, [seq], BLANK)[0]
    if np.isinf(expected):
        assert np.isinf(got)
    else:
        assert got == pytest.approx(expected, abs=1e-9)


def test_batch_with_mixed_lengths_matches_individual():
    lp = _random_log_probs(T=7, V=5, seed=3)
    seqs = [[1, 2, 3], [4], [], [2, 2], [1, 2, 3, 4]]
    batch = ctc_log_likelihoods(lp, seqs, BLANK)
    for s, b in zip(seqs, batch):
        single = ctc_log_likelihoods(lp, [s], BLANK)[0]
        assert b == pytest.approx(single, abs=1e-9)


def test_impossible_sequence_is_minus_inf():
    lp = _random_log_probs(T=2, V=4, seed=1)
    # "1 1" needs at least 3 frames (1, blank, 1)
    assert np.isneginf(ctc_log_likelihoods(lp, [[1, 1]], BLANK)[0])


def _peaky(frames, V, floor=1e-4):
    """Build CTC-like posteriors: each entry is the dominant token for that frame."""
    probs = np.full((len(frames), V), floor)
    for t, tok in enumerate(frames):
        probs[t, tok] = 1.0
    probs /= probs.sum(axis=1, keepdims=True)
    return np.log(probs)


def test_gop_high_for_correct_low_for_substitution():
    V = 6  # 0 blank, 1..5 phones
    canonical = [1, 2, 3]
    correct = _peaky([0, 1, 1, 0, 2, 0, 3, 3, 0], V)
    wrong = _peaky([0, 1, 1, 0, 4, 0, 3, 3, 0], V)  # phone 2 realised as 4
    cand = list(range(1, V))
    good = ctc_gop(correct, canonical, cand, BLANK)
    bad = ctc_gop(wrong, canonical, cand, BLANK)
    assert all(p.posterior > 0.95 for p in good.positions)
    assert bad.positions[0].posterior > 0.95
    assert bad.positions[2].posterior > 0.95
    assert bad.positions[1].posterior < 0.05
    assert bad.positions[1].best_alternative == 4


def test_gop_detects_deletion():
    V = 6
    canonical = [1, 2, 3]
    deleted = _peaky([0, 1, 1, 0, 0, 0, 3, 3, 0], V)  # phone 2 missing
    res = ctc_gop(deleted, canonical, list(range(1, V)), BLANK)
    assert res.positions[1].posterior < 0.05
    assert res.positions[1].best_alternative is None  # deletion is most likely
    assert np.exp(res.positions[1].deletion_log_posterior) > 0.9


def test_accepted_variant_is_not_penalised():
    V = 6
    canonical = [1, 2, 3]
    variant = _peaky([0, 1, 0, 5, 5, 0, 3, 0], V)  # 2 realised as accepted allophone 5
    res = ctc_gop(variant, canonical, list(range(1, V)), BLANK, accepted={1: [5]})
    pos = res.positions[1]
    assert pos.posterior < 0.05  # strict canonical posterior is low...
    assert pos.accepted_posterior > 0.95  # ...but the accepted variant counts as correct
    assert pos.best_accepted_variant == 5
    assert pos.best_alternative != 5


def test_viterbi_alignment_spans_cover_tokens_in_order():
    V = 6
    lp = _peaky([0, 1, 1, 0, 2, 0, 0, 3, 0], V)
    score, toks = ctc_viterbi_align(lp, [1, 2, 3], BLANK)
    assert np.isfinite(score)
    assert [t.token for t in toks] == [1, 2, 3]
    assert toks[0].peak_start == 1 and toks[0].peak_end == 3
    assert toks[1].peak_start == 4
    assert toks[2].peak_start == 7
    # segments tile the region between first and last peaks without overlap
    for a, b in zip(toks, toks[1:]):
        assert a.seg_end == b.seg_start


def test_greedy_decode():
    V = 6
    lp = _peaky([0, 1, 1, 0, 2, 2, 0, 2, 0], V)
    assert [t for t, _, _ in greedy_decode(lp, BLANK)] == [1, 2, 2]


def test_units_handle_multi_token_diphthongs():
    # units: 1=(1,), diphthong=(2,3), 4=(4,)
    V = 6
    canonical = [(1,), (2, 3), (4,)]
    cands = [(1,), (2, 3), (4,), (5,), (2,)]
    good = _peaky([0, 1, 0, 2, 2, 3, 0, 4, 0], V)
    bad = _peaky([0, 1, 0, 5, 5, 0, 0, 4, 0], V)  # diphthong replaced by monophthong 5
    assert ctc_gop(good, canonical, cands, BLANK).positions[1].posterior > 0.9
    res = ctc_gop(bad, canonical, cands, BLANK).positions[1]
    assert res.posterior < 0.05 and res.best_alternative == (5,)


def test_torch_backend_matches_numpy():
    torch = pytest.importorskip("torch")  # noqa: F841
    from speech_analysis.phoneme_analysis.ctc_gop import sequence_log_likelihoods

    lp = _random_log_probs(T=30, V=8, seed=11)
    seqs = [[1, 2, 3], [4, 4], [], [7, 1, 2, 2, 5], [3]]
    a = sequence_log_likelihoods(lp, seqs, BLANK, backend="numpy")
    b = sequence_log_likelihoods(lp, seqs, BLANK, backend="torch")
    np.testing.assert_allclose(a, b, rtol=1e-4, atol=1e-3)
