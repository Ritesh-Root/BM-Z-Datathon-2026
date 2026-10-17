"""Scoring back-ends behind one interface.

* ``XGBScorer``    XGBoost on the CPU (any machine).
* ``SnapMLScorer`` IBM Snap ML. On IBM z16/z17 with zDNN it runs the same
                   XGBoost trees on the Telum on-chip AI accelerator (NNPA,
                   tree_format "zdnn_tensors"); elsewhere it uses compressed
                   trees on the CPU. The format actually used is reported.

All inputs go through ``encoding.encode`` (float32, native byte order,
missing -> sentinel), exactly as during training.
"""

from __future__ import annotations

import logging
import os
import warnings
from pathlib import Path
from typing import Protocol

import numpy as np

from ..features.spec import spec_hash
from .artifacts import read_json
from .encoding import encode, snapml_compatible_json

log = logging.getLogger("vitalwatch.scorer")


class Scorer(Protocol):
    name: str
    device: str

    def predict(self, X: np.ndarray) -> np.ndarray: ...


class XGBScorer:
    name = "xgboost"

    def __init__(self, path: str | Path, nthread: int = 1):
        import xgboost as xgb

        self.booster = xgb.Booster()
        self.booster.load_model(str(path))
        self.booster.set_param({"nthread": nthread})
        self.device = "cpu"
        self.detail = f"XGBoost {xgb.__version__} (CPU, {nthread} thread)"

    def predict(self, X: np.ndarray) -> np.ndarray:
        m = self.booster.inplace_predict(encode(X), missing=np.nan, predict_type="margin")
        return 1.0 / (1.0 + np.exp(-np.asarray(m, dtype=np.float64)))


class SnapMLScorer:
    name = "snapml"

    def __init__(self, path: str | Path, tree_format: str = "auto", n_jobs: int = 1):
        import tempfile

        compat = Path(tempfile.gettempdir()) / f"vitalwatch_snapml_{os.getpid()}.json"
        snapml_compatible_json(path, compat)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            from snapml import BoostingMachineClassifier

            self.model = BoostingMachineClassifier(n_jobs=n_jobs)
            self.model.import_model(str(compat), "xgb_json", tree_format=tree_format)
        compat.unlink(missing_ok=True)
        self.warnings = [str(w.message) for w in caught]
        self.tree_format = getattr(self.model.booster_, "optimized_tree_format_", "unknown")
        self.device = "nnpa" if self.tree_format == "zdnn_tensors" else "cpu"
        self.detail = f"IBM Snap ML ({self.tree_format})"

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.asarray(self.model.predict_proba(encode(X))[:, 1], dtype=np.float64)


def check_spec(artifacts: Path) -> dict:
    meta = read_json(artifacts / "model_meta.json")
    if meta["spec_hash"] != spec_hash():
        raise RuntimeError(
            f"model was trained with feature spec {meta['spec_hash']} but this code has "
            f"{spec_hash()}; retrain with `python -m vitalwatch train`")
    return meta


def load_scorer(kind: str, artifacts: str | Path, nthread: int = 1) -> Scorer:
    """kind: 'auto' | 'xgboost' | 'snapml' | 'snapml-nnpa' | 'snapml-cpu'."""
    artifacts = Path(artifacts)
    check_spec(artifacts)
    path = artifacts / "model_xgb.json"
    if kind in ("auto", "snapml", "snapml-nnpa", "snapml-cpu"):
        fmt = {"snapml-nnpa": "zdnn_tensors", "snapml-cpu": "compress_trees"}.get(kind, "auto")
        try:
            s = SnapMLScorer(path, tree_format=fmt, n_jobs=nthread)
            if kind == "auto" and s.device != "nnpa":
                log.info("NNPA not in use (%s); using XGBoost CPU scorer", s.tree_format)
                return XGBScorer(path, nthread)
            return s
        except Exception as exc:  # snapml missing or model not importable
            if kind != "auto":
                raise
            log.info("Snap ML unavailable (%s); using XGBoost CPU scorer", exc)
    return XGBScorer(path, nthread)
