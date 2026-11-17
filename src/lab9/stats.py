"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy.stats import bootstrap

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    if len(human) != len(judge):
        raise ValueError("human and judge must have the same length")
    out = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for h, j in zip(human, judge):
        h_pos, j_pos = h == POS, j == POS
        if j_pos and h_pos:
            out["tp"] += 1
        elif j_pos:
            out["fp"] += 1
        elif h_pos:
            out["fn"] += 1
        else:
            out["tn"] += 1
    return out


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    c = confusion(human, judge)
    p_den, r_den = c["tp"] + c["fp"], c["tp"] + c["fn"]
    precision = c["tp"] / p_den if p_den else 0.0
    recall = c["tp"] / r_den if r_den else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    c = confusion(human, judge)
    n = sum(c.values())
    if n == 0:
        raise ValueError("kappa undefined: no items")
    p_o = (c["tp"] + c["tn"]) / n
    h_fail, j_fail = (c["tp"] + c["fn"]) / n, (c["tp"] + c["fp"]) / n
    p_e = h_fail * j_fail + (1 - h_fail) * (1 - j_fail)
    if math.isclose(p_e, 1.0):
        raise ValueError("kappa undefined: p_e == 1 (constant labels)")
    return (p_o - p_e) / (1 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denom = sensitivity + specificity - 1
    if denom <= 0:
        raise ValueError("Rogan-Gladen undefined: sensitivity + specificity must exceed 1")
    est = (observed_rate + specificity - 1) / denom
    return min(1.0, max(0.0, est))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    if len(a) != len(b):
        raise ValueError("paired bootstrap needs the same items in the same order")
    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if np.array_equal(x, y):
        return (0.0, 0.0, 0.0)
    diff = float(x.mean() - y.mean())
    res = bootstrap(
        (x, y),
        lambda u, v, axis=-1: np.mean(u, axis=axis) - np.mean(v, axis=axis),
        paired=True, vectorized=True, method="percentile",
        n_resamples=n_resamples, confidence_level=confidence,
        rng=np.random.default_rng(rng),
    )
    ci = res.confidence_interval
    return (diff, float(ci.low), float(ci.high))


def _check_nck(n: int, c: int, k: int) -> None:
    for name, v in (("n", n), ("c", c), ("k", k)):
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError(f"{name} must be an int")
    if n < 1 or k < 1 or c < 0 or c > n or k > n:
        raise ValueError(f"invalid (n, c, k) = ({n}, {c}, {k})")


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    _check_nck(n, c, k)
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    _check_nck(n, c, k)
    return math.comb(c, k) / math.comb(n, k)
