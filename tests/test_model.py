from __future__ import annotations

import json

import numpy as np
import pytest

from vitalwatch.data.labels import outcomes
from vitalwatch.data.splits import make_splits
from vitalwatch.model.artifacts import check_golden, read_json
from vitalwatch.model.encoding import MISSING_SENTINEL, encode, snapml_compatible_json
from vitalwatch.model.scorers import XGBScorer, load_scorer
from vitalwatch.model.train_xgb import run_training


@pytest.fixture(scope="module")
def trained(tmp_path_factory, cohort):
    d = tmp_path_factory.mktemp("art")
    split = make_splits(outcomes(cohort), seed=3)
    meta = run_training(cohort, split, d, d / "eval.npz", quick=True, log=lambda *_: None)
    return d, meta


def test_artifacts_written_and_sliced(trained):
    d, meta = trained
    for f in ("model_xgb.json", "model_meta.json", "golden.json"):
        assert (d / f).is_file()
    model = json.loads((d / "model_xgb.json").read_text())
    n_trees = len(model["learner"]["gradient_booster"]["model"]["trees"])
    assert n_trees == meta["best_iteration"] + 1 == meta["n_trees"]


def test_reloaded_model_matches_golden(trained):
    d, _ = trained
    r = check_golden(XGBScorer(d / "model_xgb.json").predict, d / "golden.json", atol=1e-6)
    assert r["ok"], r


def test_snapml_matches_xgboost_including_missing(trained):
    pytest.importorskip("snapml")
    d, _ = trained
    s = load_scorer("snapml-cpu", d)
    r = check_golden(s.predict, d / "golden.json", atol=1e-5)
    assert r["ok"], r


def test_encoding_is_native_float32_with_sentinel():
    X = np.array([[1.5, np.nan]], dtype=">f8")
    E = encode(X)
    assert E.dtype == np.float32 and E.dtype.isnative and E.flags["C_CONTIGUOUS"]
    assert E[0, 1] == np.float32(MISSING_SENTINEL)


def test_snapml_json_has_scalar_base_score(trained, tmp_path):
    d, _ = trained
    out = snapml_compatible_json(d / "model_xgb.json", tmp_path / "m.json")
    bs = json.loads(out.read_text())["learner"]["learner_model_param"]["base_score"]
    float(bs)  # parses as a plain number


def test_spec_mismatch_refuses_to_load(trained, tmp_path):
    d, _ = trained
    for f in ("model_xgb.json", "golden.json"):
        (tmp_path / f).write_bytes((d / f).read_bytes())
    meta = read_json(d / "model_meta.json")
    meta["spec_hash"] = "deadbeef"
    (tmp_path / "model_meta.json").write_text(json.dumps(meta))
    with pytest.raises(RuntimeError, match="feature spec"):
        load_scorer("xgboost", tmp_path)
