"""Platt calibration so the displayed risk is a meaningful probability.

Fitted on validation patients only: p_cal = sigmoid(a * logit(p_raw) + b).
Monotonic, so it never changes which patient ranks higher, only how the risk
reads ("12% chance the sepsis label switches on within the next hours").
"""

from __future__ import annotations

import numpy as np


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=np.float64), 1e-7, 1 - 1e-7)
    return np.log(p / (1 - p))


def fit_platt(p_raw: np.ndarray, y: np.ndarray) -> dict:
    from sklearn.linear_model import LogisticRegression

    lr = LogisticRegression(C=1e6, max_iter=1000)
    lr.fit(_logit(p_raw).reshape(-1, 1), np.asarray(y).astype(int))
    return {"method": "platt", "a": float(lr.coef_[0, 0]), "b": float(lr.intercept_[0]), "fitted_on": "val"}


def apply_calibration(p_raw: np.ndarray, cal: dict | None) -> np.ndarray:
    if not cal:
        return np.asarray(p_raw, dtype=np.float64)
    z = cal["a"] * _logit(p_raw) + cal["b"]
    return 1.0 / (1.0 + np.exp(-z))
