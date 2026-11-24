"""Patient-level early-warning metrics.

Definitions (hours since ICU admission):
* onset          t_onset = first labelled hour + 6 (PhysioNet 2019 convention)
* detection win  [t_onset - 12, t_onset + 3]; a septic patient is detected if
                 any alert falls inside it
* lead time      t_onset - first alert inside the window (>= 0 means early)
* censoring      septic patients are evaluated up to t_onset + 3 only;
                 non-septic patients over their whole stay
* burden         alerts per 100 patient-days of evaluated time
* PPV            alerts inside a detection window / all counted alerts
Patients septic on admission (POA) are reported separately and excluded from
the headline sensitivity and lead time, because their onset is unknown.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

WINDOW_BEFORE_H = 12
WINDOW_AFTER_H = 3


@dataclass
class PatientResult:
    septic: bool
    poa: bool
    hours: int
    n_alerts: int
    n_true: int
    detected: bool
    lead: float | None


def score_patient(alert_hours: list[int], septic: bool, poa: bool, t_onset: float | None,
                  n_hours: int) -> PatientResult:
    if septic:
        end = int(min(n_hours - 1, t_onset + WINDOW_AFTER_H))
        lo, hi = t_onset - WINDOW_BEFORE_H, t_onset + WINDOW_AFTER_H
        counted = [t for t in alert_hours if t <= end]
        inwin = [t for t in counted if lo <= t <= hi]
        lead = float(t_onset - inwin[0]) if inwin else None
        return PatientResult(True, poa, end + 1, len(counted), len(inwin), bool(inwin), lead)
    return PatientResult(False, False, n_hours, len(alert_hours), 0, False, None)


def aggregate(results: list[PatientResult]) -> dict:
    sep = [r for r in results if r.septic and not r.poa]
    poa = [r for r in results if r.septic and r.poa]
    hours = sum(r.hours for r in results)
    n_alerts = sum(r.n_alerts for r in results)
    n_true = sum(r.n_true for r in results)
    leads = np.array([r.lead for r in sep if r.lead is not None], dtype=float)
    n_sep = max(len(sep), 1)
    return {
        "patients": len(results),
        "septic_patients": len(sep),
        "sensitivity": round(sum(r.detected for r in sep) / n_sep, 4),
        "sensitivity_early": round(float(np.sum(leads >= 0)) / n_sep, 4),
        "sensitivity_3h": round(float(np.sum(leads >= 3)) / n_sep, 4),
        "median_lead_h": round(float(np.median(leads)), 2) if len(leads) else None,
        "lead_iqr_h": [round(float(np.percentile(leads, 25)), 2), round(float(np.percentile(leads, 75)), 2)] if len(leads) else None,
        "alerts": int(n_alerts),
        "alerts_per_100_patient_days": round(100.0 * n_alerts / max(hours / 24.0, 1e-9), 2),
        "ppv": round(n_true / n_alerts, 4) if n_alerts else None,
        "poa_patients": len(poa),
        "poa_detected": round(sum(r.detected for r in poa) / len(poa), 4) if poa else None,
        "patient_days": round(hours / 24.0, 1),
    }


def bootstrap(results: list[PatientResult],
              keys=("sensitivity_early", "alerts_per_100_patient_days", "median_lead_h", "ppv"),
              n: int = 200, seed: int = 0) -> dict:
    """Percentile 95% CI from resampling whole patients with replacement."""
    rng = np.random.default_rng(seed)
    idx = np.arange(len(results))
    samples = {k: [] for k in keys}
    for _ in range(n):
        pick = rng.choice(idx, size=len(idx), replace=True)
        agg = aggregate([results[i] for i in pick])
        for k in keys:
            if agg[k] is not None:
                samples[k].append(agg[k])
    return {k: [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)]
            for k, v in samples.items() if v}


def paired_bootstrap(a: list[PatientResult], b: list[PatientResult],
                     keys=("sensitivity_early", "alerts_per_100_patient_days"),
                     n: int = 200, seed: int = 0) -> dict:
    """95% CI of the difference (a minus b) between two policies run on the SAME patients.

    ``a[i]`` and ``b[i]`` must be the results for patient i under each policy. The same
    resampled patients are used for both, so the CI reflects the paired comparison and not
    two independent estimates.
    """
    if len(a) != len(b):
        raise ValueError("paired bootstrap needs the same patients in the same order")
    rng = np.random.default_rng(seed)
    idx = np.arange(len(a))
    samples = {k: [] for k in keys}
    for _ in range(n):
        pick = rng.choice(idx, size=len(idx), replace=True)
        agg_a = aggregate([a[i] for i in pick])
        agg_b = aggregate([b[i] for i in pick])
        for k in keys:
            if agg_a[k] is not None and agg_b[k] is not None:
                samples[k].append(agg_a[k] - agg_b[k])
    return {k: [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)]
            for k, v in samples.items() if v}


def bootstrap_hourly_auc(patients_y: list[np.ndarray], patients_s: list[np.ndarray],
                         n: int = 200, seed: int = 0) -> dict:
    """95% CI of hourly AUROC / AUPRC from resampling whole patients (rows stay together)."""
    from sklearn.metrics import average_precision_score, roc_auc_score

    rng = np.random.default_rng(seed)
    idx = np.arange(len(patients_y))
    roc, pr = [], []
    for _ in range(n):
        pick = rng.choice(idx, size=len(idx), replace=True)
        y = np.concatenate([patients_y[i] for i in pick])
        s = np.concatenate([patients_s[i] for i in pick])
        if y.min() == y.max():
            continue
        roc.append(roc_auc_score(y, s))
        pr.append(average_precision_score(y, s))
    return {"auroc": [round(float(np.percentile(roc, 2.5)), 4), round(float(np.percentile(roc, 97.5)), 4)],
            "auprc": [round(float(np.percentile(pr, 2.5)), 4), round(float(np.percentile(pr, 97.5)), 4)]}
