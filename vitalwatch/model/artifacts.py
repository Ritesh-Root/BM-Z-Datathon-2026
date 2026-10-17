"""Portable model artifacts: JSON metadata and golden predictions.

Everything here is text (JSON) so it reads identically on x86 (little-endian)
and IBM Z (big-endian). ``check_golden`` proves on the target machine that the
model gives the same answers it gave where it was trained.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: str | Path, obj) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1, sort_keys=True), encoding="utf-8")


def read_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _nan_to_none(row: np.ndarray) -> list:
    return [None if (isinstance(x, float) and math.isnan(x)) else float(x) for x in row.tolist()]


def write_golden(path: str | Path, X: np.ndarray, p: np.ndarray, margin: np.ndarray) -> None:
    write_json(path, {
        "n": int(len(X)),
        "features": [_nan_to_none(r) for r in np.asarray(X, dtype=np.float64)],
        "p": [float(x) for x in p],
        "margin": [float(x) for x in margin],
    })


def load_golden(path: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    g = read_json(path)
    X = np.array([[np.nan if v is None else v for v in r] for r in g["features"]], dtype=np.float64)
    return X, np.array(g["p"]), np.array(g["margin"])


def check_golden(predict, path: str | Path, atol: float = 1e-5) -> dict:
    X, p_ref, _ = load_golden(path)
    p = np.asarray(predict(X), dtype=np.float64)
    diff = np.abs(p - p_ref)
    return {"n": int(len(p)), "max_abs_diff": float(diff.max()), "mean_abs_diff": float(diff.mean()),
            "atol": atol, "ok": bool(diff.max() <= atol)}
