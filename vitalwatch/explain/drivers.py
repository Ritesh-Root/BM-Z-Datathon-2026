"""Why did VitalWatch alert? Plain-language drivers from exact tree SHAP values.

XGBoost computes exact per-feature contributions (TreeSHAP, ``pred_contribs``)
in log-odds. We group the 142 features back to the clinical variable they come
from (e.g. Resp, Resp__mean6, Resp__slope6 -> "Respiratory rate"), keep only
variables a clinician can act on, and describe each with its current value and
recent change. Care-process and context features (hours in ICU, age, how often
labs were drawn) still count in the risk but are never shown as drivers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..features.spec import FEATURE_INDEX, FEATURE_NAMES, FEATURES
from ..model.encoding import encode
from ..schema import DISPLAY, VITALS

_BASE = np.array([f.base_var for f in FEATURES])
_ACTIONABLE = np.array([f.actionable for f in FEATURES])

DERIVED_LABELS = {
    "shock_index": ("Shock index (HR / systolic BP)", "{:.2f}"),
    "pulse_pressure": ("Pulse pressure", "{:.0f} mmHg"),
    "bun_cr": ("BUN / creatinine ratio", "{:.0f}"),
    "sf_ratio": ("SpO2 / FiO2 ratio", "{:.0f}"),
    "on_o2": ("Supplemental oxygen", None),
    "sofa_partial": ("Organ dysfunction (partial SOFA)", "{:.0f} points"),
    "news2": ("NEWS2 score", "{:.0f}"),
    "qsofa": ("qSOFA criteria met", "{:.0f} of 2"),
    "sirs": ("SIRS criteria met", "{:.0f} of 4"),
    "care_intensity": ("Care intensity (tests ordered)", None),
}


@dataclass
class Driver:
    var: str
    label: str
    text: str
    logit: float

    def to_dict(self) -> dict:
        return {"var": self.var, "label": self.label, "text": self.text, "logit": round(self.logit, 3)}


class Explainer:
    def __init__(self, model_path: str | Path):
        import xgboost as xgb

        self._xgb = xgb
        self.booster = xgb.Booster()
        self.booster.load_model(str(model_path))
        self.booster.set_param({"nthread": 1})

    def contributions(self, X: np.ndarray) -> np.ndarray:
        """[n, 143] log-odds contributions (last column is the bias)."""
        d = self._xgb.DMatrix(encode(X), missing=np.nan, feature_names=list(FEATURE_NAMES))
        return np.asarray(self.booster.predict(d, pred_contribs=True), dtype=np.float64)


def group_by_variable(contrib_row: np.ndarray, actionable_only: bool = True) -> list[tuple[str, float]]:
    c = contrib_row[: len(FEATURES)]
    mask = _ACTIONABLE if actionable_only else np.ones(len(FEATURES), dtype=bool)
    sums: dict[str, float] = {}
    for base, val, m in zip(_BASE, c, mask):
        if m:
            sums[str(base)] = sums.get(str(base), 0.0) + float(val)
    return sorted(sums.items(), key=lambda kv: kv[1], reverse=True)


def _fmt(v: float, var: str) -> str:
    if var == "Temp":
        return f"{v:.1f}"
    if var in ("pH",):
        return f"{v:.2f}"
    if var in ("FiO2",):
        return f"{v:.2f}"
    if abs(v) >= 10 or var in VITALS:
        return f"{v:.0f}"
    return f"{v:.1f}"


def driver_text(var: str, x: np.ndarray) -> tuple[str, str]:
    """(label, text) for one variable using the current feature row."""
    g = lambda name: float(x[FEATURE_INDEX[name]]) if name in FEATURE_INDEX else math.nan  # noqa: E731
    if var in DISPLAY and var in FEATURE_INDEX:
        label, unit = DISPLAY[var]
        v = g(var)
        if math.isnan(v):
            return label, "not measured"
        text = f"{_fmt(v, var)} {unit}".strip()
        if var in VITALS:
            d6 = g(f"{var}__d6")
            if not math.isnan(d6) and abs(d6) >= (0.3 if var == "Temp" else 1):
                text += f", {'up' if d6 > 0 else 'down'} {_fmt(abs(d6), var)} in 6 h"
        else:
            hrs = g(f"{var}__tsl")
            if not math.isnan(hrs):
                text += " (now)" if hrs == 0 else f" ({hrs:.0f} h ago)"
            d24 = g(f"{var}__d24")
            if not math.isnan(d24) and abs(d24) > 1e-9:
                text += f", {'up' if d24 > 0 else 'down'} {_fmt(abs(d24), var)} in 24 h"
        return label, text
    label, fmt = DERIVED_LABELS.get(var, (var, "{:.2f}"))
    v = g(var)
    if var == "on_o2":
        return label, "yes" if v == 1 else "no"
    if fmt is None or math.isnan(v):
        return label, "elevated"
    return label, fmt.format(v)


def top_drivers(contrib_row: np.ndarray, x: np.ndarray, k: int = 4) -> list[Driver]:
    grouped = group_by_variable(contrib_row)
    out = []
    for var, val in grouped:
        if val <= 0 or len(out) >= k:
            break
        label, text = driver_text(var, x)
        out.append(Driver(var, label, text, val))
    return out


def global_drivers(contrib: np.ndarray, top: int = 15) -> list[dict]:
    """Mean |contribution| per variable over many rows (all features, labelled by group)."""
    c = np.abs(contrib[:, : len(FEATURES)])
    sums: dict[str, float] = {}
    kind: dict[str, bool] = {}
    for j, f in enumerate(FEATURES):
        sums[f.base_var] = sums.get(f.base_var, 0.0) + float(c[:, j].mean())
        kind[f.base_var] = kind.get(f.base_var, False) or f.actionable
    ranked = sorted(sums.items(), key=lambda kv: kv[1], reverse=True)[:top]
    out = []
    for var, v in ranked:
        label = DISPLAY.get(var, (DERIVED_LABELS.get(var, (var,))[0],))[0]
        out.append({"var": var, "label": label, "mean_abs_logit": round(v, 4), "clinical": kind[var]})
    return out
