"""Single source of truth for the bedside data layout.

The column layout follows the public PhysioNet / Computing in Cardiology
Challenge 2019 files (one pipe-separated row per ICU hour). Our synthetic
generator writes exactly the same layout, so every downstream module has a
single code path.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

VITALS: tuple[str, ...] = ("HR", "O2Sat", "Temp", "SBP", "MAP", "DBP", "Resp")
LABS: tuple[str, ...] = (
    "BaseExcess", "HCO3", "FiO2", "pH", "PaCO2", "SaO2", "AST", "BUN",
    "Alkalinephos", "Calcium", "Chloride", "Creatinine", "Bilirubin_direct",
    "Glucose", "Lactate", "Magnesium", "Phosphate", "Potassium",
    "Bilirubin_total", "TroponinI", "Hct", "Hgb", "PTT", "WBC", "Fibrinogen",
    "Platelets",
)
CONTEXT: tuple[str, ...] = ("Age", "Gender", "Unit1", "Unit2", "HospAdmTime", "ICULOS")
LABEL = "SepsisLabel"

# Full value-column order in the PSV files (EtCO2 sits between the vitals and
# the labs). The label is the 41st column and is kept separately.
VALUE_COLUMNS: tuple[str, ...] = VITALS + ("EtCO2",) + LABS + CONTEXT
ALL_COLUMNS: tuple[str, ...] = VALUE_COLUMNS + (LABEL,)
COL_INDEX: dict[str, int] = {c: i for i, c in enumerate(VALUE_COLUMNS)}

# Variables that are actually measured at the bedside / in the lab and are
# forward-filled by the feature pipeline. EtCO2 is almost never recorded in
# this dataset, so it is not used as a feature.
MEASURED: tuple[str, ...] = VITALS + LABS

# Physiologically plausible ranges. Values outside are treated as recording
# errors and become "not measured" before any forward-filling.
BOUNDS: dict[str, tuple[float, float]] = {
    "HR": (20, 250), "O2Sat": (50, 100), "Temp": (30, 43), "SBP": (40, 300),
    "MAP": (20, 200), "DBP": (10, 200), "Resp": (3, 70), "EtCO2": (0, 100),
    "BaseExcess": (-40, 40), "HCO3": (3, 60), "FiO2": (0.1, 1.0), "pH": (6.5, 7.9),
    "PaCO2": (5, 150), "SaO2": (20, 100), "AST": (1, 20000), "BUN": (1, 300),
    "Alkalinephos": (5, 5000), "Calcium": (2, 20), "Chloride": (60, 160),
    "Creatinine": (0.1, 30), "Bilirubin_direct": (0, 60), "Glucose": (10, 1500),
    "Lactate": (0.1, 40), "Magnesium": (0.3, 10), "Phosphate": (0.3, 20),
    "Potassium": (1, 12), "Bilirubin_total": (0, 80), "TroponinI": (0, 500),
    "Hct": (5, 70), "Hgb": (2, 25), "PTT": (10, 250), "WBC": (0.1, 300),
    "Fibrinogen": (20, 1500), "Platelets": (1, 2000),
    "Age": (0, 120), "Gender": (0, 1), "Unit1": (0, 1), "Unit2": (0, 1),
    "HospAdmTime": (-100000, 100), "ICULOS": (0, 10000),
}

# Display labels and units used by the dashboard, driver text and notes.
DISPLAY: dict[str, tuple[str, str]] = {
    "HR": ("Heart rate", "bpm"), "O2Sat": ("SpO2", "%"), "Temp": ("Temperature", "\u00b0C"),
    "SBP": ("Systolic BP", "mmHg"), "MAP": ("Mean arterial pressure", "mmHg"),
    "DBP": ("Diastolic BP", "mmHg"), "Resp": ("Respiratory rate", "/min"),
    "EtCO2": ("End-tidal CO2", "mmHg"), "BaseExcess": ("Base excess", "mmol/L"),
    "HCO3": ("Bicarbonate", "mmol/L"), "FiO2": ("FiO2", ""), "pH": ("pH", ""),
    "PaCO2": ("PaCO2", "mmHg"), "SaO2": ("SaO2", "%"), "AST": ("AST", "IU/L"),
    "BUN": ("BUN", "mg/dL"), "Alkalinephos": ("Alkaline phosphatase", "IU/L"),
    "Calcium": ("Calcium", "mg/dL"), "Chloride": ("Chloride", "mmol/L"),
    "Creatinine": ("Creatinine", "mg/dL"), "Bilirubin_direct": ("Direct bilirubin", "mg/dL"),
    "Glucose": ("Glucose", "mg/dL"), "Lactate": ("Lactate", "mmol/L"),
    "Magnesium": ("Magnesium", "mmol/dL"), "Phosphate": ("Phosphate", "mg/dL"),
    "Potassium": ("Potassium", "mmol/L"), "Bilirubin_total": ("Total bilirubin", "mg/dL"),
    "TroponinI": ("Troponin I", "ng/mL"), "Hct": ("Hematocrit", "%"),
    "Hgb": ("Hemoglobin", "g/dL"), "PTT": ("PTT", "s"), "WBC": ("White cell count", "x10^3/uL"),
    "Fibrinogen": ("Fibrinogen", "mg/dL"), "Platelets": ("Platelets", "x10^3/uL"),
    "Age": ("Age", "y"), "Gender": ("Sex", ""), "Unit1": ("MICU", ""), "Unit2": ("SICU", ""),
    "HospAdmTime": ("Hours from hospital to ICU admission", "h"), "ICULOS": ("Hours in ICU", "h"),
}


def clean_values(x: np.ndarray, cols: Sequence[str] = VALUE_COLUMNS) -> np.ndarray:
    """Return a cleaned float64 copy of raw values.

    * FiO2 recorded as a percentage (> 1) is converted to a fraction.
    * Values outside BOUNDS become NaN (treated as "not measured").

    Works on any array whose last axis follows ``cols``. Shared by the offline
    (training) and online (live) feature paths so both see identical inputs.
    """
    out = np.array(x, dtype=np.float64, copy=True)
    for j, c in enumerate(cols):
        col = out[..., j]
        if c == "FiO2":
            pct = col > 1.0
            col[pct] = col[pct] / 100.0
        lo, hi = BOUNDS.get(c, (-np.inf, np.inf))
        with np.errstate(invalid="ignore"):
            bad = (col < lo) | (col > hi)
        col[bad] = np.nan
    return out
