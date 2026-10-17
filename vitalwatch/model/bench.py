"""Inference benchmark: the same VitalWatch model on every available engine.

Arms (each runs in its own subprocess so thread pools never interfere):
  xgb-cpu-1t     XGBoost, 1 thread
  xgb-cpu-mt     XGBoost, all cores
  snapml-cpu     IBM Snap ML, compressed trees on the CPU
  snapml-nnpa    IBM Snap ML on the IBM Telum on-chip AI accelerator (zdnn_tensors);
                 only reported when the accelerator is really used
For every arm and batch size we report latency per call (p50/p95/p99), rows
per second, and agreement with XGBoost (max probability difference and
identical alert decisions at the deployed threshold). Unavailable arms are
reported as such; numbers are never estimated.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ARMS = ("xgb-cpu-1t", "xgb-cpu-mt", "snapml-cpu", "snapml-nnpa")
BATCHES = (1, 8, 32, 128, 512, 2048, 8192)


def _load(arm: str, artifacts: Path):
    from .scorers import SnapMLScorer, XGBScorer, check_spec

    check_spec(artifacts)
    path = artifacts / "model_xgb.json"
    ncpu = os.cpu_count() or 1
    if arm == "xgb-cpu-1t":
        return XGBScorer(path, 1)
    if arm == "xgb-cpu-mt":
        return XGBScorer(path, ncpu)
    if arm == "snapml-cpu":
        return SnapMLScorer(path, "compress_trees", n_jobs=1)
    if arm == "snapml-nnpa":
        s = SnapMLScorer(path, "zdnn_tensors", n_jobs=1)
        if s.tree_format != "zdnn_tensors":
            raise RuntimeError(f"Snap ML did not use the accelerator (format {s.tree_format})")
        return s
    raise ValueError(arm)


def run_arm(arm: str, artifacts: Path, data_npz: Path, batches=BATCHES, min_calls: int = 100,
            max_seconds: float = 3.0) -> dict:
    """Executed inside the subprocess for one arm."""
    with np.load(data_npz) as z:
        X = z["X"].astype(np.float64)
    try:
        scorer = _load(arm, artifacts)
    except Exception as exc:
        return {"arm": arm, "status": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}
    out = {"arm": arm, "status": "ok", "detail": getattr(scorer, "detail", arm), "batches": []}
    rng = np.random.default_rng(0)
    for bsz in batches:
        if bsz > len(X):
            continue
        for _ in range(10):  # warm-up
            scorer.predict(X[:bsz])
        times = []
        t_end = time.perf_counter() + max_seconds
        while len(times) < min_calls or (time.perf_counter() < t_end and len(times) < 20 * min_calls):
            start = int(rng.integers(0, len(X) - bsz + 1))
            t0 = time.perf_counter_ns()
            scorer.predict(X[start:start + bsz])
            times.append((time.perf_counter_ns() - t0) / 1e6)
            if time.perf_counter() > t_end and len(times) >= 10:
                break
        a = np.array(times)
        out["batches"].append({
            "batch": bsz, "calls": len(a), "p50_ms": round(float(np.percentile(a, 50)), 4),
            "p95_ms": round(float(np.percentile(a, 95)), 4), "p99_ms": round(float(np.percentile(a, 99)), 4),
            "rows_per_s": round(bsz / (float(np.median(a)) / 1e3), 1),
        })
    out["pred"] = scorer.predict(X[: min(len(X), 8192)]).tolist()
    return out


def environment() -> dict:
    from .nnpa import detect_nnpa

    env = {"host": socket.gethostname(), "python": platform.python_version(), "cpus": os.cpu_count(),
           "accelerator": detect_nnpa(), "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    for k in ("OMP_NUM_THREADS", "SNAPML_ZDNN_LIB", "ZDNN_ENABLE_PRECHECK"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def run_benchmark(artifacts: Path, X: np.ndarray, results_dir: Path, arms=ARMS, quick: bool = False,
                  log=print) -> dict:
    from .artifacts import read_json
    from .calibration import apply_calibration

    meta = read_json(artifacts / "model_meta.json")
    theta = read_json(artifacts / "policy.json")["theta_on"] if (artifacts / "policy.json").exists() else 0.05
    batches = (1, 32, 512) if quick else BATCHES
    tmp = Path(tempfile.mkdtemp(prefix="vw_bench_")) / "X.npz"
    np.savez(tmp, X=np.ascontiguousarray(X, dtype="<f8"))
    results = []
    for arm in arms:
        log(f"benchmarking {arm} ...")
        cmd = [sys.executable, "-m", "vitalwatch", "bench-arm", arm, "--data", str(tmp),
               "--batches", ",".join(map(str, batches))]
        if quick:
            cmd.append("--quick")
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        try:
            results.append(json.loads(p.stdout.strip().splitlines()[-1]))
        except Exception:
            results.append({"arm": arm, "status": "error", "reason": (p.stderr or p.stdout)[-400:]})
    ref = next((r for r in results if r["arm"] == "xgb-cpu-1t" and r["status"] == "ok"), None)
    cal = meta.get("calibration")
    if ref:
        p_ref = np.array(ref["pred"])
        d_ref = apply_calibration(p_ref, cal) >= theta
        for r in results:
            if r.get("status") == "ok":
                p = np.array(r["pred"])
                r["agreement_vs_xgboost"] = {
                    "rows": int(len(p)), "max_abs_diff": float(np.max(np.abs(p - p_ref))),
                    "alert_decisions_identical": float(np.mean((apply_calibration(p, cal) >= theta) == d_ref)),
                }
    for r in results:
        r.pop("pred", None)
    report = {"environment": environment(), "model": {"n_trees": meta.get("n_trees"), "features": len(meta["feature_names"]),
                                                     "source": meta.get("source")},
              "threshold": theta, "arms": results}
    acc = report["environment"]["accelerator"]
    name = f"bench_{acc['arch']}_{report['environment']['host'][:20]}.json"
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / name).write_text(json.dumps(report, indent=1), encoding="utf-8")
    report["file"] = str(results_dir / name)
    return report
