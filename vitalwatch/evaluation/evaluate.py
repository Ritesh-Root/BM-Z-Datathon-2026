"""Evaluate VitalWatch against bedside early-warning scores at matched alarm burden.

All operating points (thresholds, policy settings) are chosen on the
validation patients only, then reported once on the held-out test patients.
"""

from __future__ import annotations

import multiprocessing as mp
import os
from dataclasses import replace
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from ..alerts.policy import PolicyParams, raw_params, simulate_fast, threshold_crossings
from ..data.labels import LABEL_SHIFT_H
from ..model.artifacts import write_json
from .metrics import aggregate, bootstrap, score_patient

TARGET_BURDEN = 30.0  # alerts per 100 patient-days (about one alert per bed every 3 days)
BASELINES = {"news2": [3, 4, 5, 6, 7, 8, 9, 10, 12], "qsofa": [1, 2], "sirs": [1, 2, 3, 4]}
BASELINE_POINTS = [("news2", 5), ("news2", 7), ("qsofa", 2), ("sirs", 2), ("sirs", 3)]
SCORE_KEYS = ("model", "news2", "qsofa", "sirs")


def load_eval(path: str | Path) -> dict:
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k].astype(z[k].dtype.newbyteorder("=")) for k in z.files}


def patients_for(ev: dict, split: str) -> list[dict]:
    rows = ev[f"{split}_rows"]
    p_model = ev[f"{split}_p"]
    pidx = ev["pidx"][rows]
    starts = np.flatnonzero(np.r_[True, pidx[1:] != pidx[:-1]])
    ends = np.r_[starts[1:], len(rows)]
    out = []
    for a, b in zip(starts, ends):
        r = rows[a:b]
        lab = ev["labels"][r]
        pos = np.flatnonzero(lab == 1)
        septic = len(pos) > 0
        t_label = int(pos[0]) if septic else None
        age = ev["f_Age"][r[0]]
        out.append({
            "septic": septic, "poa": septic and t_label == 0,
            "t_onset": float(t_label + LABEL_SHIFT_H) if septic else None,
            "n_hours": int(b - a), "hospital": int(ev["hospital"][pidx[a]]),
            "gender": None if np.isnan(ev["f_Gender"][r[0]]) else int(ev["f_Gender"][r[0]]),
            "age": None if np.isnan(age) else float(age),
            "scores": {"model": p_model[a:b], "news2": ev["f_news2"][r],
                       "qsofa": ev["f_qsofa"][r], "sirs": ev["f_sirs"][r]},
            "labels": lab,
        })
    return out


def run_policy(patients: list[dict], key: str, P: PolicyParams):
    res = []
    for pt in patients:
        alerts = simulate_fast(pt["scores"][key], P)
        res.append(score_patient([t for t, _ in alerts], pt["septic"], pt["poa"], pt["t_onset"], pt["n_hours"]))
    return res


_POOL_PATIENTS: list[dict] = []


def _eval_config(args):
    key, P = args
    return P, aggregate(run_policy(_POOL_PATIENTS, key, P))


def evaluate_grid(patients: list[dict], key: str, configs: list[PolicyParams], workers: int) -> list[tuple]:
    global _POOL_PATIENTS
    _POOL_PATIENTS = patients
    jobs = [(key, P) for P in configs]
    if workers > 1 and "fork" in mp.get_all_start_methods():
        with mp.get_context("fork").Pool(workers) as pool:
            return pool.map(_eval_config, jobs, chunksize=max(1, len(jobs) // (workers * 4)))
    return [_eval_config(j) for j in jobs]


def _best(results: list[tuple], max_burden: float) -> tuple | None:
    ok = [(P, m) for P, m in results if m["alerts_per_100_patient_days"] <= max_burden]
    if not ok:
        return None
    return max(ok, key=lambda pm: (pm[1]["sensitivity_early"], pm[1]["median_lead_h"] or -99, pm[1]["ppv"] or 0))


def policy_grid(val_scores: np.ndarray) -> list[PolicyParams]:
    qs = np.quantile(val_scores, np.r_[np.linspace(0.70, 0.89, 6), np.linspace(0.90, 0.998, 18)])
    grid = []
    for th in np.unique(np.round(qs, 4)):
        for sustain in (1, 2, 3):
            for off_ratio in (0.6, 0.8):
                for rise in (False, True):
                    grid.append(PolicyParams(theta_on=float(th), theta_off=float(th * off_ratio),
                                             sustain_h=sustain, rise_enabled=rise))
    return grid


def raw_grid(val_scores: np.ndarray) -> list[PolicyParams]:
    qs = np.quantile(val_scores, np.linspace(0.50, 0.999, 50))
    return [raw_params(float(t)) for t in np.unique(np.round(qs, 5))]


def _hourly(patients: list[dict], key: str) -> dict:
    y, s = [], []
    for pt in patients:
        n = pt["n_hours"]
        end = int(min(n - 1, pt["t_onset"] + 3)) + 1 if pt["septic"] else n
        y.append(pt["labels"][:end])
        s.append(pt["scores"][key][:end])
    y, s = np.concatenate(y), np.concatenate(s)
    return {"auroc": round(float(roc_auc_score(y, s)), 4), "auprc": round(float(average_precision_score(y, s)), 4)}


def _age_band(a):
    if a is None:
        return "unknown"
    return "18-49" if a < 50 else "50-69" if a < 70 else "70+"


def subgroups(patients: list[dict], P: PolicyParams) -> list[dict]:
    groups = {
        "sex": lambda pt: {0: "female", 1: "male"}.get(pt["gender"], "unknown"),
        "age": lambda pt: _age_band(pt["age"]),
        "hospital": lambda pt: "A" if pt["hospital"] == 0 else "B",
    }
    out = []
    for gname, fn in groups.items():
        buckets: dict[str, list] = {}
        for pt in patients:
            buckets.setdefault(fn(pt), []).append(pt)
        for label, pts in sorted(buckets.items()):
            agg = aggregate(run_policy(pts, "model", P))
            out.append({"group": gname, "value": label, **{k: agg[k] for k in (
                "patients", "septic_patients", "sensitivity_early", "median_lead_h",
                "alerts_per_100_patient_days", "ppv")}})
    return out


def run_evaluation(eval_path: Path, results_dir: Path, artifacts_dir: Path, source: str,
                   target_burden: float = TARGET_BURDEN, workers: int | None = None, log=print) -> dict:
    workers = workers or min(4, os.cpu_count() or 1)
    ev = load_eval(eval_path)
    val, test = patients_for(ev, "val"), patients_for(ev, "test")
    val_scores = np.concatenate([pt["scores"]["model"] for pt in val])

    # 1. Model: full policy grid and plain-threshold grid on validation.
    grid = evaluate_grid(val, "model", policy_grid(val_scores), workers)
    raw = evaluate_grid(val, "model", raw_grid(val_scores), workers)
    chosen = _best(grid, target_burden) or min(grid, key=lambda pm: pm[1]["alerts_per_100_patient_days"])
    P = chosen[0]
    log(f"selected policy on val: {P}")
    test_res = run_policy(test, "model", P)
    selected = {"params": P.to_dict(), "target_burden": target_burden, "selected_on": "val",
                "val": chosen[1], "test": aggregate(test_res), "test_ci95": bootstrap(test_res)}

    raw_chosen = _best(raw, target_burden)
    ablation = None
    if raw_chosen:
        ablation = {"raw_threshold": raw_chosen[0].theta_on, "val": raw_chosen[1],
                    "test": aggregate(run_policy(test, "model", raw_chosen[0]))}

    crossings = sum(threshold_crossings(pt["scores"]["model"], P.theta_on) for pt in test)
    alarm_reduction = {"policy_alerts": selected["test"]["alerts"], "plain_threshold_alarms": int(crossings),
                       "theta": P.theta_on}

    # 2. Baselines through the same snooze logic, and the model matched to each.
    baselines = []
    for name, th in BASELINE_POINTS:
        bp = raw_params(float(th))
        b_val = aggregate(run_policy(val, name, bp))
        b_test = aggregate(run_policy(test, name, bp))
        m = _best(grid + raw, b_val["alerts_per_100_patient_days"])
        row = {"baseline": name, "threshold": th, "val": b_val, "test": b_test}
        if m:
            row["vitalwatch_params"] = m[0].to_dict()
            row["vitalwatch_test"] = aggregate(run_policy(test, "model", m[0]))
        baselines.append(row)

    # 3. Curves on test for the chart (plain thresholds for every score).
    curves = {}
    for key, ths in [("model", [p.theta_on for p in raw_grid(val_scores)])] + [(k, v) for k, v in BASELINES.items()]:
        pts = []
        for th in ths:
            agg = aggregate(run_policy(test, key, raw_params(float(th))))
            pts.append({"threshold": th, "burden": agg["alerts_per_100_patient_days"],
                        "sensitivity_early": agg["sensitivity_early"], "median_lead_h": agg["median_lead_h"]})
        curves[key] = pts
    curves["vitalwatch_policy"] = [{"burden": selected["test"]["alerts_per_100_patient_days"],
                                    "sensitivity_early": selected["test"]["sensitivity_early"]}]

    leads = [r.lead for r in test_res if r.septic and not r.poa and r.lead is not None]
    report = {
        "source": source,
        "data_note": "SYNTHETIC data generated by VitalWatch (PhysioNet layout); not real patients"
                     if source == "synthetic" else "PhysioNet/CinC Challenge 2019 held-out test patients",
        "n_patients": {"val": len(val), "test": len(test)},
        "hourly_test": {k: _hourly(test, k) for k in SCORE_KEYS},
        "selected_policy": selected,
        "ablation_plain_threshold_same_burden": ablation,
        "alarm_reduction_test": alarm_reduction,
        "baselines_matched_burden": baselines,
        "curves_test": curves,
        "subgroups_test": subgroups(test, P),
        "lead_times_test": leads,
    }
    results_dir.mkdir(parents=True, exist_ok=True)
    write_json(results_dir / f"metrics_{source}.json", report)
    write_json(artifacts_dir / "policy.json", {**P.to_dict(), "target_burden": target_burden,
                                                "selected_on": "val", "source": source})
    return report


def tune_for_demo(P: PolicyParams, **changes) -> PolicyParams:
    return replace(P, **changes)
