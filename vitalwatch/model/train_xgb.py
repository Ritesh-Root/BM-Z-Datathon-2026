"""Train the VitalWatch XGBoost model and export portable artifacts.

Outputs (artifacts/):
  model_xgb.json   XGBoost JSON (text, endian-safe; also the format IBM Snap ML imports)
  model_meta.json  feature spec hash, data source, sizes, versions, validation metrics
  golden.json      256 reference rows + predictions for on-target verification
and data/processed/<source>_eval.npz with per-row validation/test scores and the
bedside-score baselines, consumed by ``vitalwatch evaluate``.
"""

from __future__ import annotations

import os
import platform
import time
from pathlib import Path

import numpy as np
import xgboost as xgb
from sklearn.metrics import average_precision_score, roc_auc_score

from ..data.labels import outcomes
from ..data.loader import Cohort
from ..features.offline import build_features
from ..features.spec import FEATURE_INDEX, FEATURE_NAMES, spec_hash
from .artifacts import sha256_file, write_golden, write_json
from .encoding import MISSING_SENTINEL, encode

PARAMS_FULL = dict(objective="binary:logistic", eval_metric=["auc", "aucpr"], tree_method="hist",
                   max_depth=5, min_child_weight=10, eta=0.05, subsample=0.8, colsample_bytree=0.6,
                   reg_lambda=2.0, max_bin=256, seed=2026)
PARAMS_QUICK = dict(PARAMS_FULL, max_depth=4, eta=0.1)
ROUNDS_FULL, ROUNDS_QUICK = 3000, 300
CENSOR_AFTER_ONSET_H = 3


def row_frame(c: Cohort) -> dict[str, np.ndarray]:
    """Per-row bookkeeping: patient index, hour, onset, eligibility for training."""
    outs = outcomes(c)
    pidx = c.patient_index()
    t_in = c.row_in_patient()
    onset = np.array([o.t_onset if o.septic else np.inf for o in outs])[pidx]
    keep = t_in <= onset + CENSOR_AFTER_ONSET_H
    return {"pidx": pidx, "t_in": t_in, "onset": onset, "keep": keep}


def _mask_for(c: Cohort, pidx: np.ndarray, pids: list[str]) -> np.ndarray:
    want = np.isin(c.pids, np.array(pids))
    return want[pidx]


def train_model(X: np.ndarray, y: np.ndarray, Xva: np.ndarray, yva: np.ndarray,
                quick: bool = False, nthread: int | None = None) -> tuple[xgb.Booster, dict]:
    params = dict(PARAMS_QUICK if quick else PARAMS_FULL)
    params["nthread"] = nthread or os.cpu_count() or 1
    dtr = xgb.DMatrix(encode(X), label=y, missing=np.nan, feature_names=list(FEATURE_NAMES))
    dva = xgb.DMatrix(encode(Xva), label=yva, missing=np.nan, feature_names=list(FEATURE_NAMES))
    evals_result: dict = {}
    t0 = time.time()
    booster = xgb.train(params, dtr, num_boost_round=ROUNDS_QUICK if quick else ROUNDS_FULL,
                        evals=[(dva, "val")], early_stopping_rounds=50 if quick else 150,
                        evals_result=evals_result, verbose_eval=False)
    best = int(booster.best_iteration)
    # xgb.train returns every round; keep only the trees up to the best one.
    booster = booster[: best + 1]
    info = {"best_iteration": best, "n_trees": best + 1, "train_seconds": round(time.time() - t0, 1),
            "params": {k: v for k, v in params.items() if k != "nthread"}}
    return booster, info


def predict_margin(booster: xgb.Booster, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    margin = booster.inplace_predict(encode(X), missing=np.nan, predict_type="margin")
    p = 1.0 / (1.0 + np.exp(-margin))
    return np.asarray(p, dtype=np.float64), np.asarray(margin, dtype=np.float64)


def run_training(c: Cohort, split: dict, artifacts_dir: Path, eval_path: Path,
                 quick: bool = False, log=print) -> dict:
    t0 = time.time()
    X = build_features(c)
    log(f"features: {X.shape} in {time.time() - t0:.1f}s")
    rf = row_frame(c)
    y = c.labels.astype(np.float32)
    m_tr = _mask_for(c, rf["pidx"], split["train"]) & rf["keep"]
    m_va_fit = _mask_for(c, rf["pidx"], split["val"]) & rf["keep"]
    booster, info = train_model(X[m_tr], y[m_tr], X[m_va_fit], y[m_va_fit], quick=quick)
    log(f"trained {info['n_trees']} trees in {info['train_seconds']}s")

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifacts_dir / "model_xgb.json"
    booster.save_model(str(model_path))

    metrics = {}
    eval_arrays = {}
    for name in ("val", "test"):
        m = _mask_for(c, rf["pidx"], split[name])
        p, _ = predict_margin(booster, X[m])
        k = rf["keep"][m]
        metrics[name] = {
            "auroc": round(float(roc_auc_score(y[m][k], p[k])), 4),
            "auprc": round(float(average_precision_score(y[m][k], p[k])), 4),
            "rows": int(k.sum()), "positive_rate": round(float(y[m][k].mean()), 4),
        }
        eval_arrays[f"{name}_rows"] = np.flatnonzero(m)
        eval_arrays[f"{name}_p"] = p
    log(f"val {metrics['val']}  test {metrics['test']}")

    # Per-row arrays for evaluation (no features needed later).
    keep_cols = ["news2", "qsofa", "sirs", "Age", "Gender"]
    eval_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        eval_path,
        pidx=rf["pidx"].astype("<i8"), t_in=rf["t_in"].astype("<i8"),
        labels=c.labels.astype("<i1"), hospital=c.hospital.astype("<i1"),
        offsets=c.offsets.astype("<i8"),
        **{k: v.astype("<i8") if k.endswith("_rows") else v.astype("<f8") for k, v in eval_arrays.items()},
        **{f"f_{k}": X[:, FEATURE_INDEX[k]].astype("<f8") for k in keep_cols},
    )

    # Golden rows: a fixed random sample of test rows.
    rng = np.random.default_rng(7)
    test_rows = eval_arrays["test_rows"]
    pick = np.sort(rng.choice(test_rows, size=min(256, len(test_rows)), replace=False))
    p_g, m_g = predict_margin(booster, X[pick])
    write_golden(artifacts_dir / "golden.json", X[pick], p_g, m_g)

    meta = {
        "model": "xgboost", "file": model_path.name, "model_sha256": sha256_file(model_path),
        "spec_hash": spec_hash(), "feature_names": list(FEATURE_NAMES), "source": c.source,
        "quick": quick, "n_patients": {k: len(v) for k, v in split.items()},
        "n_train_rows": int(m_tr.sum()), "metrics": metrics, **info,
        "trained_on": {"arch": platform.machine(), "python": platform.python_version(),
                       "xgboost": xgb.__version__, "numpy": np.__version__},
        "censor_after_onset_h": CENSOR_AFTER_ONSET_H,
        "missing_encoding": {"sentinel": MISSING_SENTINEL},
    }
    write_json(artifacts_dir / "model_meta.json", meta)
    return meta
