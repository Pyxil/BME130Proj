"""Dynamic Time Warping (vectorised along anti-diagonals, no compiled extensions)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class DTWResult:
    cost: float  # accumulated cost / (N + M)
    path: np.ndarray  # (L, 2) index pairs (i into X, j into Y)


def pairwise_euclidean(X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """Euclidean distances divided by sqrt(dims) so costs are comparable across feature sizes."""
    x2 = np.sum(X**2, axis=1)[:, None]
    y2 = np.sum(Y**2, axis=1)[None, :]
    d2 = np.maximum(x2 + y2 - 2 * X @ Y.T, 0.0)
    return np.sqrt(d2) / np.sqrt(X.shape[1])


def dtw(X: np.ndarray, Y: np.ndarray, band: float = 0.35, C: np.ndarray | None = None) -> DTWResult:
    """Symmetric DTW with steps (1,0), (0,1), (1,1) and a Sakoe-Chiba style band.

    ``band`` is the maximum allowed deviation from the diagonal, as a fraction
    of the normalised time axis; it prevents degenerate alignments.
    """
    C = pairwise_euclidean(X, Y) if C is None else C
    N, M = C.shape
    if N == 0 or M == 0:
        return DTWResult(float("inf"), np.zeros((0, 2), dtype=int))
    ii, jj = np.meshgrid(np.arange(N), np.arange(M), indexing="ij")
    allowed = np.abs(ii / max(N - 1, 1) - jj / max(M - 1, 1)) <= band
    allowed[0, 0] = allowed[N - 1, M - 1] = True
    Cm = np.where(allowed, C, np.inf)

    D = np.full((N + 1, M + 1), np.inf)
    D[0, 0] = 0.0
    for k in range(2, N + M + 1):  # k = i + j in 1-indexed coordinates
        i = np.arange(max(1, k - M), min(N, k - 1) + 1)
        j = k - i
        best = np.minimum(np.minimum(D[i - 1, j - 1], D[i - 1, j]), D[i, j - 1])
        D[i, j] = Cm[i - 1, j - 1] + best
    total = D[N, M]
    if not np.isfinite(total):
        return DTWResult(float("inf"), np.zeros((0, 2), dtype=int))

    # backtrack
    path = [(N - 1, M - 1)]
    i, j = N, M
    while (i, j) != (1, 1):
        options = [(D[i - 1, j - 1], i - 1, j - 1), (D[i - 1, j], i - 1, j), (D[i, j - 1], i, j - 1)]
        _, i, j = min(options, key=lambda o: o[0])
        if i == 0 or j == 0:
            break
        path.append((i - 1, j - 1))
    return DTWResult(float(total / (N + M)), np.array(path[::-1], dtype=int))


def local_tempo_deviation(path: np.ndarray, window: int = 10) -> float:
    """Spread of local alignment slopes (log scale).

    A path with uniform slope (the user is uniformly faster or slower than the
    reference) gives ~0.  Large values mean some parts were stretched or
    compressed much more than others.
    """
    if len(path) < 2 * window:
        return 0.0
    slopes = []
    for s in range(0, len(path) - window, max(1, window // 2)):
        di = path[s + window, 0] - path[s, 0]
        dj = path[s + window, 1] - path[s, 1]
        slopes.append(np.log((di + 1) / (dj + 1)))
    return float(np.std(slopes)) if slopes else 0.0
