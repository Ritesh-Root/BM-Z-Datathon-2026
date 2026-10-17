"""Feature math shared by the offline (training) and online (live) paths.

Both paths only differ in how they gather history (vectorised over all rows
vs. ring buffers per bed). Everything computed from that history goes through
``assemble`` below, so training and serving use the same arithmetic.
"""

from __future__ import annotations

import warnings

import numpy as np

from ..clinical import scores
from ..schema import LABS, MEASURED, VITALS
from .spec import FFILL_COLUMNS, LAB_TRENDS, N_FEATURES, WINDOW_LONG, WINDOW_SHORT, WORST24

FF_INDEX = {c: i for i, c in enumerate(FFILL_COLUMNS)}
VITAL_INDEX = {v: i for i, v in enumerate(VITALS)}
LAB_COLS = np.array([FF_INDEX[v] for v in LABS])
VITAL_COLS = np.array([FF_INDEX[v] for v in VITALS])
LAB_TREND_COLS = np.array([FF_INDEX[v] for v in LAB_TRENDS])
N_MEASURED = len(MEASURED)


def window_stats(win: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """nan-aware mean / min / max / std (ddof=0, NaN if < 2 values) over the last axis."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        n = np.sum(~np.isnan(win), axis=-1)
        mean = np.nanmean(win, axis=-1)
        mn = np.nanmin(win, axis=-1)
        mx = np.nanmax(win, axis=-1)
        std = np.nanstd(win, axis=-1)
    std = np.where(n >= 2, std, np.nan)
    return mean, mn, mx, std


def window_slope(win: np.ndarray, min_points: int = 3) -> np.ndarray:
    """Least-squares slope per hour over the last axis (oldest -> newest)."""
    w = win.shape[-1]
    x = np.arange(w, dtype=np.float64) - (w - 1)
    mask = ~np.isnan(win)
    n = mask.sum(axis=-1)
    safe_n = np.maximum(n, 1)
    xm = np.where(mask, x, 0.0).sum(axis=-1) / safe_n
    y = np.where(mask, win, 0.0)
    ym = y.sum(axis=-1) / safe_n
    dx = np.where(mask, x - xm[..., None], 0.0)
    num = (dx * (y - ym[..., None])).sum(axis=-1)
    den = (dx * dx).sum(axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        slope = num / den
    return np.where((n >= min_points) & (den > 0), slope, np.nan)


def derived(ff: np.ndarray) -> list[np.ndarray]:
    """Derived physiology and bedside scores from current forward-filled values."""
    g = lambda name: ff[:, FF_INDEX[name]]  # noqa: E731
    hr, sbp, dbp, map_, rr, spo2, temp = g("HR"), g("SBP"), g("DBP"), g("MAP"), g("Resp"), g("O2Sat"), g("Temp")
    fio2 = g("FiO2")
    with np.errstate(invalid="ignore", divide="ignore"):
        shock = hr / sbp
        pp = sbp - dbp
        bun_cr = g("BUN") / g("Creatinine")
        fio2_eff = np.where(np.isnan(fio2), 0.21, fio2)
        sf = spo2 / fio2_eff
        on_o2 = (fio2 > 0.211).astype(np.float64)
    return [
        shock, pp, bun_cr, sf, on_o2,
        scores.sofa_partial(g("Platelets"), g("Bilirubin_total"), map_, g("Creatinine")),
        scores.news2_partial(rr, spo2, on_o2, sbp, hr, temp),
        scores.qsofa_partial(rr, sbp),
        scores.sirs(temp, hr, rr, g("PaCO2"), g("WBC")),
    ]


def assemble(ff: np.ndarray, tsl: np.ndarray, w24: np.ndarray, lab_ref: np.ndarray,
             n_labs_24h: np.ndarray, n_vitals_missing_6h: np.ndarray) -> np.ndarray:
    """Build the [n, 142] feature matrix.

    ff      [n, 39]     current forward-filled values (FFILL_COLUMNS order)
    tsl     [n, 33]     hours since each measured variable was last observed
    w24     [n, 7, 24]  forward-filled vitals for hours t-23..t (NaN before admission)
    lab_ref [n, 5]      forward-filled LAB_TRENDS values 24 h earlier (or at admission)
    """
    n = ff.shape[0]
    out = np.empty((n, N_FEATURES), dtype=np.float64)
    col = 0

    out[:, col:col + N_MEASURED] = ff[:, :N_MEASURED]
    col += N_MEASURED
    out[:, col:col + N_MEASURED] = tsl
    col += N_MEASURED

    w6 = np.ascontiguousarray(w24[..., WINDOW_LONG - WINDOW_SHORT:])
    mean, mn, mx, std = window_stats(w6)
    slope = window_slope(w6)
    for v in range(len(VITALS)):
        out[:, col:col + 5] = np.stack([mean[:, v], mn[:, v], mx[:, v], std[:, v], slope[:, v]], axis=1)
        col += 5

    now = w24[..., -1]
    d1 = now - w24[..., -2]
    d6 = now - w24[..., -1 - 6]
    for v in range(len(VITALS)):
        out[:, col] = d1[:, v]
        out[:, col + 1] = d6[:, v]
        col += 2

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for name, how in WORST24:
            series = w24[:, VITAL_INDEX[name], :]
            out[:, col] = np.nanmax(series, axis=-1) if how == "max" else np.nanmin(series, axis=-1)
            col += 1

    out[:, col:col + len(LAB_TRENDS)] = ff[:, LAB_TREND_COLS] - lab_ref
    col += len(LAB_TRENDS)

    out[:, col] = n_labs_24h
    out[:, col + 1] = n_vitals_missing_6h
    col += 2

    for arr in derived(ff):
        out[:, col] = arr
        col += 1

    g = lambda name: ff[:, FF_INDEX[name]]  # noqa: E731
    unit = np.where(g("Unit1") == 1, 1.0, np.where(g("Unit2") == 1, 2.0, 0.0))
    for arr in (g("Age"), g("Gender"), unit, g("HospAdmTime"), g("ICULOS")):
        out[:, col] = arr
        col += 1
    assert col == N_FEATURES
    return out
