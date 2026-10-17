"""Vectorised feature builder for training and evaluation (all rows at once)."""

from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from ..data.loader import Cohort
from ..schema import COL_INDEX, clean_values
from .kernels import LAB_COLS, LAB_TREND_COLS, VITAL_COLS, assemble
from .spec import FFILL_COLUMNS, N_FEATURES, WINDOW_LONG

_FF_SRC = np.array([COL_INDEX[c] for c in FFILL_COLUMNS])
N_MEASURED = 33


def ffill_by_patient(v: np.ndarray, starts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Causal forward-fill within each patient.

    v      [n, k] values (NaN = not measured)
    starts [n]    index of the first row of the patient that owns each row
    Returns (ff [n, k], last_obs_row [n, k] or -1).
    """
    n = v.shape[0]
    rows = np.arange(n, dtype=np.int64)[:, None]
    idx = np.where(np.isnan(v), -1, rows)
    last = np.maximum.accumulate(idx, axis=0)
    last = np.where(last < starts[:, None], -1, last)
    safe = np.maximum(last, 0)
    ff = np.take_along_axis(v, safe, axis=0)
    ff = np.where(last >= 0, ff, np.nan)
    return ff, last


def _features_for_rows(values: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    """Features for a block of whole patients (offsets local to the block)."""
    n = len(values)
    lens = np.diff(offsets)
    starts = np.repeat(offsets[:-1], lens)
    t_in = np.arange(n) - starts

    clean = clean_values(values)
    src = clean[:, _FF_SRC]
    ff, last = ffill_by_patient(src, starts)
    rows = np.arange(n)[:, None]
    tsl = np.where(last[:, :N_MEASURED] >= 0, (rows - last[:, :N_MEASURED]).astype(np.float64), np.nan)

    # 24-hour history of forward-filled vitals, oldest -> newest.
    vit = ff[:, VITAL_COLS]
    pad = np.full((WINDOW_LONG - 1, vit.shape[1]), np.nan)
    view = sliding_window_view(np.vstack([pad, vit]), WINDOW_LONG, axis=0)  # [n, 7, 24]
    lag = (WINDOW_LONG - 1) - np.arange(WINDOW_LONG)
    valid = t_in[:, None] >= lag[None, :]
    w24 = np.where(valid[:, None, :], view, np.nan)

    # Lab values 24 h earlier, or at admission when the stay is shorter.
    ref_rows = np.maximum(np.arange(n) - 24, starts)
    lab_ref = ff[ref_rows][:, LAB_TREND_COLS]

    # Care-intensity counts from what was actually observed.
    obs = ~np.isnan(src)
    lab_cnt = obs[:, LAB_COLS].sum(axis=1)
    vit_cnt = obs[:, VITAL_COLS].sum(axis=1)
    cs_lab = np.concatenate([[0], np.cumsum(lab_cnt)])
    cs_vit = np.concatenate([[0], np.cumsum(vit_cnt)])
    i = np.arange(n)
    lo24 = np.maximum(i - 23, starts)
    lo6 = np.maximum(i - 5, starts)
    n_labs_24h = (cs_lab[i + 1] - cs_lab[lo24]).astype(np.float64)
    rows6 = i - lo6 + 1
    n_vit_missing = (len(VITAL_COLS) * rows6 - (cs_vit[i + 1] - cs_vit[lo6])).astype(np.float64)

    return assemble(ff, tsl, w24, lab_ref, n_labs_24h, n_vit_missing)


def build_features(c: Cohort, chunk_rows: int = 200_000) -> np.ndarray:
    """[N, 142] float64 features for every row of the cohort."""
    out = np.empty((len(c.values), N_FEATURES), dtype=np.float64)
    p = 0
    while p < c.n_patients:
        q = p + 1
        while q < c.n_patients and c.offsets[q + 1] - c.offsets[p] <= chunk_rows:
            q += 1
        lo, hi = int(c.offsets[p]), int(c.offsets[q])
        local = (c.offsets[p:q + 1] - lo).astype(np.int64)
        out[lo:hi] = _features_for_rows(c.values[lo:hi], local)
        p = q
    return out
