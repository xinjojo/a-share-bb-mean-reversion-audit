"""A-Share Alpha Factory — multiple testing control.

Benjamini-Hochberg FDR + 累计尝试计数（TOTAL HYPOTHESIS ATTEMPTS）。
预留 Deflated Sharpe Ratio / CSCV 接口（Phase 1 再实现）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def benjamini_hochberg(p_values: np.ndarray | list, alpha: float = 0.05) -> list[bool]:
    """BH-FDR: returns list of booleans (True = survives FDR at alpha)."""
    p = np.asarray(p_values, dtype=float)
    n = len(p)
    if n == 0:
        return []
    order = np.argsort(p)
    sorted_p = p[order]
    threshold = alpha * np.arange(1, n + 1) / n
    # largest k with p_k <= alpha*k/n
    passed = np.where(sorted_p <= threshold)[0]
    k = (passed.max() + 1) if len(passed) else 0
    reject = np.zeros(n, dtype=bool)
    reject[order[:k]] = True
    return list(reject)


def hypothesis_attempt_count(expressions, horizons, universes, labels,
                             variants=1) -> int:
    """严格计数：表达式 × horizon × universe × label × variant 全部算尝试。"""
    return len(expressions) * len(horizons) * len(universes) * len(labels) * variants


def deflated_sharpe_ratio(  # interface reserved (Phase 1)
        sharpe: float, n_obs: int, n_trials: int, skew: float = 0.0,
        kurt: float = 3.0) -> float:
    """Deflated Sharpe (Bailey & Lopez de Prado) — placeholder interface."""
    # standard error of Sharpe
    se = np.sqrt((1 + 0.5 * sharpe ** 2 - skew * sharpe + (kurt - 3) / 4 * sharpe ** 2)
                 / max(n_obs - 1, 1))
    z = np.sqrt(max(n_trials, 1))
    # approximate expected max Sharpe under null
    e0 = np.sqrt(2 * np.log(z))
    expected_max = e0 + (np.euler_gamma - np.log(np.pi)) / (2 * np.sqrt(2 * np.log(z)))
    expected_max *= se
    return sharpe - expected_max


def pbo_cscv(  # interface reserved (Phase 1)
        returns: pd.DataFrame) -> dict:
    """Probability of Backtest Overfitting via CSCV — interface reserved."""
    raise NotImplementedError('CSCV reserved for Phase 1')
