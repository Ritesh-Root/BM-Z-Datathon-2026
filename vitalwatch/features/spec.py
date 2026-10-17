"""Feature specification: names, order and metadata for the 142 model inputs.

The same specification drives offline training features and live features,
and its hash is stored with every trained model. The server refuses to load a
model whose feature hash does not match the running code.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from ..schema import CONTEXT, LABS, MEASURED, VITALS

KERNEL_VERSION = "1"

WINDOW_SHORT = 6
WINDOW_LONG = 24
WORST24 = (("HR", "max"), ("Resp", "max"), ("Temp", "max"), ("Temp", "min"), ("MAP", "min"), ("O2Sat", "min"))
LAB_TRENDS = ("Lactate", "Creatinine", "Platelets", "WBC", "Bilirubin_total")
DERIVED = ("shock_index", "pulse_pressure", "bun_cr", "sf_ratio", "on_o2",
           "sofa_partial", "news2", "qsofa", "sirs")
CONTEXT_FEATURES = ("Age", "Gender", "unit", "HospAdmTime", "ICULOS")
# Columns that are forward-filled: all measured variables plus context.
FFILL_COLUMNS = MEASURED + CONTEXT


@dataclass(frozen=True)
class FeatureDef:
    name: str
    base_var: str
    kind: str
    group: str
    actionable: bool  # shown to clinicians as an alert driver


def _build() -> tuple[FeatureDef, ...]:
    f: list[FeatureDef] = []
    for v in MEASURED:
        f.append(FeatureDef(v, v, "last", "vital" if v in VITALS else "lab", True))
    for v in MEASURED:
        f.append(FeatureDef(f"{v}__tsl", v, "hours_since_measured", "care", False))
    for v in VITALS:
        for stat in ("mean6", "min6", "max6", "std6", "slope6"):
            f.append(FeatureDef(f"{v}__{stat}", v, stat, "vital_trend", True))
    for v in VITALS:
        f.append(FeatureDef(f"{v}__d1", v, "delta1", "vital_trend", True))
        f.append(FeatureDef(f"{v}__d6", v, "delta6", "vital_trend", True))
    for v, how in WORST24:
        f.append(FeatureDef(f"{v}__{how}24", v, f"{how}24", "vital_trend", True))
    for v in LAB_TRENDS:
        f.append(FeatureDef(f"{v}__d24", v, "delta24", "lab_trend", True))
    f.append(FeatureDef("n_labs_24h", "care_intensity", "count", "care", False))
    f.append(FeatureDef("n_vitals_missing_6h", "care_intensity", "count", "care", False))
    for d in DERIVED:
        f.append(FeatureDef(d, d, "derived", "score", True))
    for c in CONTEXT_FEATURES:
        f.append(FeatureDef(c, c, "context", "context", False))
    return tuple(f)


FEATURES: tuple[FeatureDef, ...] = _build()
FEATURE_NAMES: tuple[str, ...] = tuple(fd.name for fd in FEATURES)
FEATURE_INDEX: dict[str, int] = {n: i for i, n in enumerate(FEATURE_NAMES)}
N_FEATURES = len(FEATURES)


def spec_hash() -> str:
    payload = json.dumps({"kernel": KERNEL_VERSION, "features": [asdict(f) for f in FEATURES],
                          "context": list(CONTEXT), "labs": list(LABS)}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


assert N_FEATURES == 142, N_FEATURES
