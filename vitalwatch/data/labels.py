"""Outcome definitions on top of the hourly SepsisLabel.

In the PhysioNet 2019 data the label is switched on 6 hours *before* the
clinical sepsis onset (t_sepsis). So for a septic patient:

    t_label = first hour with SepsisLabel == 1
    t_onset = t_label + 6          (hours since ICU admission, 0-based rows)

Patients whose label is already 1 in their first hour are "present on
admission" (POA): their true onset may be earlier than t_label + 6, so lead
time for them is left-censored and they are reported separately.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .loader import Cohort

LABEL_SHIFT_H = 6


@dataclass(frozen=True)
class Outcome:
    pid: str
    septic: bool
    t_label: int | None
    t_onset: float | None
    n_hours: int
    poa: bool
    hospital: int


def outcomes(c: Cohort) -> list[Outcome]:
    out = []
    for p in range(c.n_patients):
        lab = c.labels[c.patient_slice(p)]
        pos = np.flatnonzero(lab == 1)
        if len(pos):
            t_label = int(pos[0])
            out.append(Outcome(str(c.pids[p]), True, t_label, float(t_label + LABEL_SHIFT_H),
                               len(lab), t_label == 0, int(c.hospital[p])))
        else:
            out.append(Outcome(str(c.pids[p]), False, None, None, len(lab), False, int(c.hospital[p])))
    return out


def summarize(outs: list[Outcome], labels: np.ndarray) -> dict:
    n = len(outs)
    septic = [o for o in outs if o.septic]
    hours = np.array([o.n_hours for o in outs])
    return {
        "patients": n,
        "rows": int(len(labels)),
        "septic_patients": len(septic),
        "septic_rate": round(len(septic) / max(n, 1), 4),
        "positive_row_rate": round(float(np.mean(labels)), 4) if len(labels) else 0.0,
        "present_on_admission": sum(o.poa for o in septic),
        "median_stay_h": float(np.median(hours)) if n else 0.0,
        "median_onset_h": float(np.median([o.t_onset for o in septic])) if septic else None,
    }
