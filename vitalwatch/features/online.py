"""Live feature state for a whole ward, updated one ICU hour at a time.

Each bed keeps the minimum history needed (last values, ring buffers for the
24-hour window and observation counts). ``update`` processes all beds that
received a new row in one vectorised call, so scoring a 10,000-bed hospital is
one batch per tick.
"""

from __future__ import annotations

import numpy as np

from ..schema import COL_INDEX, VITALS, clean_values
from .kernels import LAB_COLS, LAB_TREND_COLS, VITAL_COLS, assemble
from .spec import FFILL_COLUMNS, N_FEATURES, WINDOW_LONG

_FF_SRC = np.array([COL_INDEX[c] for c in FFILL_COLUMNS])
N_MEASURED = 33
N_VIT = len(VITAL_COLS)


class WardFeatureState:
    def __init__(self, n_beds: int):
        self.n_beds = n_beds
        k = len(FFILL_COLUMNS)
        self.last_val = np.full((n_beds, k), np.nan)
        self.last_t = np.full((n_beds, k), -1, dtype=np.int64)
        self.t = np.full(n_beds, -1, dtype=np.int64)            # hour index of the latest row
        self.ring_vit = np.full((n_beds, WINDOW_LONG, N_VIT), np.nan)   # oldest -> newest
        self.ring_lab = np.full((n_beds, 25, len(LAB_TREND_COLS)), np.nan)
        self.first_lab = np.full((n_beds, len(LAB_TREND_COLS)), np.nan)
        self.ring_labcnt = np.zeros((n_beds, 24), dtype=np.int64)
        self.ring_vitcnt = np.zeros((n_beds, 6), dtype=np.int64)
        self.last_ff = np.full((n_beds, k), np.nan)

    def reset(self, bed: int) -> None:
        """New patient in this bed."""
        self.last_val[bed] = np.nan
        self.last_t[bed] = -1
        self.t[bed] = -1
        self.ring_vit[bed] = np.nan
        self.ring_lab[bed] = np.nan
        self.first_lab[bed] = np.nan
        self.ring_labcnt[bed] = 0
        self.ring_vitcnt[bed] = 0
        self.last_ff[bed] = np.nan

    def update(self, raw: np.ndarray, active: np.ndarray) -> np.ndarray:
        """raw [n_beds, 40] new hourly rows; active [n_beds] bool.

        Returns [n_beds, 142] features (NaN rows for inactive beds)."""
        out = np.full((self.n_beds, N_FEATURES), np.nan)
        a = np.flatnonzero(active)
        if len(a) == 0:
            return out
        src = clean_values(raw[a])[:, _FF_SRC]
        obs = ~np.isnan(src)
        self.t[a] += 1
        t = self.t[a]

        lv = self.last_val[a]
        lt = self.last_t[a]
        lv = np.where(obs, src, lv)
        lt = np.where(obs, t[:, None], lt)
        self.last_val[a] = lv
        self.last_t[a] = lt
        ff = lv
        self.last_ff[a] = ff
        tsl = np.where(lt[:, :N_MEASURED] >= 0,
                       (t[:, None] - lt[:, :N_MEASURED]).astype(np.float64), np.nan)

        rv = self.ring_vit[a]
        rv[:, :-1] = rv[:, 1:]
        rv[:, -1] = ff[:, VITAL_COLS]
        self.ring_vit[a] = rv
        w24 = np.ascontiguousarray(rv.transpose(0, 2, 1))

        rl = self.ring_lab[a]
        rl[:, :-1] = rl[:, 1:]
        rl[:, -1] = ff[:, LAB_TREND_COLS]
        self.ring_lab[a] = rl
        first = self.first_lab[a]
        first = np.where((t == 0)[:, None], ff[:, LAB_TREND_COLS], first)
        self.first_lab[a] = first
        lab_ref = np.where((t >= 24)[:, None], rl[:, 0], first)

        rc = self.ring_labcnt[a]
        rc[:, :-1] = rc[:, 1:]
        rc[:, -1] = obs[:, LAB_COLS].sum(axis=1)
        self.ring_labcnt[a] = rc
        vc = self.ring_vitcnt[a]
        vc[:, :-1] = vc[:, 1:]
        vc[:, -1] = obs[:, VITAL_COLS].sum(axis=1)
        self.ring_vitcnt[a] = vc
        rows6 = np.minimum(t + 1, 6)
        n_labs = rc.sum(axis=1).astype(np.float64)
        n_vmiss = (N_VIT * rows6 - vc.sum(axis=1)).astype(np.float64)

        out[a] = assemble(ff, tsl, w24, lab_ref, n_labs, n_vmiss)
        return out

    def snapshot(self, bed: int) -> dict:
        """Current forward-filled values and hours since measured, for the UI."""
        t = int(self.t[bed])
        vals = {}
        for j, name in enumerate(FFILL_COLUMNS):
            v = self.last_val[bed, j]
            if not np.isnan(v):
                vals[name] = {"value": float(v), "hours_ago": int(t - self.last_t[bed, j])}
        hist = {name: [None if np.isnan(x) else float(x) for x in self.ring_vit[bed, :, i]]
                for i, name in enumerate(VITALS)}
        return {"hour": t, "values": vals, "vitals_24h": hist}
