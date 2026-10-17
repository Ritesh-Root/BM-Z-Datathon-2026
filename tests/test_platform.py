from __future__ import annotations

import json
import platform

import numpy as np

from vitalwatch.config import load_config, resolve
from vitalwatch.model.bench import run_benchmark
from vitalwatch.model.nnpa import detect_nnpa


def test_detect_nnpa_never_raises():
    info = detect_nnpa()
    json.dumps(info)
    assert info["arch"] == platform.machine()
    if info["arch"] != "s390x":
        assert info["nnpa_usable"] is False


def test_quick_benchmark_reports_unavailable_arms_honestly(tmp_path):
    from vitalwatch.features.spec import N_FEATURES

    cfg = load_config()
    X = np.random.default_rng(0).normal(size=(600, N_FEATURES))
    r = run_benchmark(resolve(cfg, "artifacts_dir"), X, tmp_path, arms=("xgb-cpu-1t", "snapml-nnpa"),
                      quick=True, log=lambda *_: None)
    arms = {a["arm"]: a for a in r["arms"]}
    assert arms["xgb-cpu-1t"]["status"] == "ok"
    assert arms["xgb-cpu-1t"]["agreement_vs_xgboost"]["alert_decisions_identical"] == 1.0
    if platform.machine() != "s390x":
        assert arms["snapml-nnpa"]["status"] in ("unavailable", "error")
