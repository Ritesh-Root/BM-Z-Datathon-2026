"""Scalability test: how long one ward tick takes as the hospital grows.

Runs the real engine (features, model, alert policy, explanations and audit
for every alert) without pacing, the web server or the language model, for
100 to 10,000 simultaneous beds, and reports per-stage tick latency.
"""

from __future__ import annotations

import json
import platform
import resource
import socket
import tempfile
import time
from pathlib import Path

import numpy as np


def run_loadtest(cfg: dict, source: str, beds_list=(100, 1000, 5000, 10000), hours: int = 12,
                 log=print) -> dict:
    from ..alerts.policy import PolicyParams
    from ..config import resolve
    from ..data.loader import load_cohort_npz
    from ..explain.drivers import Explainer
    from ..explain.notes import NoteService
    from ..model.artifacts import read_json
    from ..model.nnpa import detect_nnpa
    from ..model.scorers import load_scorer
    from ..privacy.audit import AuditLog
    from ..privacy.pseudonym import Pseudonymizer
    from ..stream.engine import Engine
    from ..stream.hub import Hub
    from ..stream.replay import BedAssignment, ReplaySource, WardScenario

    data = resolve(cfg, "data_dir") / "processed"
    art = resolve(cfg, "artifacts_dir")
    cohort = load_cohort_npz(data / f"{source}.npz")
    scorer = load_scorer(cfg["scorer"]["kind"], art, calibrated=True)
    explainer = Explainer(art / "model_xgb.json")
    policy = PolicyParams.from_dict(read_json(art / "policy.json"))
    rng = np.random.default_rng(1)
    rows = []
    for n_beds in beds_list:
        pids = [str(p) for p in cohort.pids]
        order = rng.permutation(len(pids))
        assign = [BedAssignment(b, pids[order[b % len(pids)]], 0) for b in range(n_beds)]
        queue = [pids[i] for i in rng.permutation(len(pids))][:n_beds * 2]
        scen = WardScenario(n_beds, assign, queue, source)
        tmp = Path(tempfile.mkdtemp(prefix="vw_load_"))
        hub = Hub()
        audit = AuditLog(tmp / "audit.jsonl", b"k" * 32)
        eng = Engine(ReplaySource(cohort, scen), scorer, explainer, policy, NoteService(None, hub.publish), hub,
                     audit, Pseudonymizer(b"p" * 32), tick_seconds=0)
        eng.tick()  # warm-up hour
        t0 = time.perf_counter()
        for _ in range(hours):
            eng.tick()
        wall = time.perf_counter() - t0
        lat = eng.lat.summary()
        row = {"beds": n_beds, "hours": hours, "alerts": eng.alerts_fired,
               "tick_ms_p50": lat["tick_total"]["p50"], "tick_ms_p99": lat["tick_total"]["p99"],
               "features_ms_p50": lat["features"]["p50"], "score_ms_p50": lat["score"]["p50"],
               "policy_explain_audit_ms_p50": lat["policy_explain_audit"]["p50"],
               "bed_hours_per_s": round(n_beds * hours / wall, 1),
               "max_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)}
        row["capacity_beds_at_1_reading_per_min"] = int(n_beds * 60_000 / max(row["tick_ms_p99"], 1e-6))
        log(json.dumps(row))
        rows.append(row)
    import os

    report = {"environment": {"host": socket.gethostname(), "python": platform.python_version(), "cpus": os.cpu_count(),
                              "accelerator": detect_nnpa(), "scorer": scorer.detail},
              "source": source, "rows": rows}
    out = resolve(cfg, "results_dir") / f"loadtest_{platform.machine()}.json"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    report["file"] = str(out)
    return report
