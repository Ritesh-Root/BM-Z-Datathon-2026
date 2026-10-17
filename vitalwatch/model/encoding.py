"""Model input encoding shared by training and every scorer.

Missing values are encoded as a large negative sentinel instead of NaN. Trees
then learn an explicit "was not measured" branch (missing sorts below every
real value). This keeps predictions identical across XGBoost and IBM Snap ML,
whose NaN handling differs from XGBoost's learned default directions.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

MISSING_SENTINEL = -1.0e9


def encode(X: np.ndarray) -> np.ndarray:
    """float32, C-contiguous, native byte order, NaN -> sentinel."""
    Xf = np.ascontiguousarray(X, dtype=np.float32)
    return np.where(np.isnan(Xf), np.float32(MISSING_SENTINEL), Xf)


def snapml_compatible_json(src: str | Path, dst: str | Path) -> Path:
    """Rewrite an XGBoost 3.x JSON model in the layout IBM Snap ML parses:
    compact separators and a scalar ``base_score`` (XGBoost 3 stores a vector)."""
    d = json.loads(Path(src).read_text(encoding="utf-8"))
    lmp = d["learner"]["learner_model_param"]
    bs = str(lmp.get("base_score", "0.5")).strip()
    if bs.startswith("[") and bs.endswith("]"):
        parts = [p for p in bs[1:-1].split(",") if p.strip()]
        if len(parts) != 1:
            raise ValueError("multi-target base_score is not supported by this exporter")
        lmp["base_score"] = parts[0].strip()
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
    return Path(dst)
