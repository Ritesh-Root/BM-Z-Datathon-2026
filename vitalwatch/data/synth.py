"""Synthetic ICU cohort generator (our own physiology model).

Used when the real PhysioNet 2019 data cannot be downloaded (and for tests).
It writes exactly the PhysioNet file layout: one pipe-separated ``.psv`` file
per patient with one row per ICU hour and the literal string ``NaN`` for values
that were not measured. Everything produced here is clearly labelled SYNTHETIC
in the UI and in reports.

Model in one paragraph: each patient has six latent organ-system severities
(cardiovascular, respiratory, thermoregulatory/inflammatory, metabolic, renal,
coagulation/liver). They wander around a personal baseline (Ornstein-Uhlenbeck
noise), get hit by short "confounder" episodes that touch one or two systems
(post-operative fever, pain tachycardia, atelectasis), and in ~10% of
non-septic patients a non-infectious shock ramp (cardiovascular + metabolic,
no fever). Septic patients get a sigmoid ramp across all systems with
patient-specific weights that starts 6-20 hours before onset, so some septic
patients look obvious and some are subtle. Lab draws become more frequent as
the patient gets sicker (informative missingness), as in real ICUs.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from ..schema import ALL_COLUMNS, LABS, VALUE_COLUMNS

LABEL_SHIFT_H = 6
CHANNELS = ("cardio", "resp", "thermo", "metab", "renal", "coag")

PANELS: dict[str, tuple[str, ...]] = {
    "bmp": ("BUN", "Creatinine", "Glucose", "Potassium", "Chloride", "HCO3",
            "Calcium", "Magnesium", "Phosphate"),
    "cbc": ("WBC", "Hgb", "Hct", "Platelets"),
    "abg": ("pH", "PaCO2", "BaseExcess", "SaO2", "FiO2", "HCO3"),
    "lft": ("AST", "Alkalinephos", "Bilirubin_total", "Bilirubin_direct"),
    "coag": ("PTT", "Fibrinogen"),
    "trop": ("TroponinI",),
}


@dataclass
class SynthConfig:
    n_patients: int = 4000
    sepsis_rate: float = 0.08
    seed: int = 7
    los_median_h: float = 36.0
    confounder_rate: float = 0.8
    hidden_shock_rate: float = 0.20
    hospital_b_frac: float = 0.5


def _ar1(rng: np.random.Generator, n: int, sd: float, phi: float = 0.6) -> np.ndarray:
    e = rng.normal(0.0, sd, n)
    out = np.empty(n)
    acc = 0.0
    for i in range(n):
        acc = phi * acc + e[i]
        out[i] = acc
    return out


def _bump(t: np.ndarray, start: float, dur: float, amp: float) -> np.ndarray:
    x = (t - start) / max(dur, 1.0)
    return np.where((x >= 0) & (x <= 1), amp * np.sin(np.pi * np.clip(x, 0, 1)), 0.0)


def _sigmoid_ramp(t: np.ndarray, center: float, width: float, amp: float) -> np.ndarray:
    return amp / (1.0 + np.exp(-(t - center) / max(width, 0.5)))


def generate_patient(rng: np.random.Generator, cfg: SynthConfig, hospital: int) -> tuple[np.ndarray, dict]:
    """Return (rows [T, 41] incl. SepsisLabel, metadata) for one patient."""
    septic = bool(rng.random() < cfg.sepsis_rate)
    if septic:
        t_onset = int(rng.integers(3, 90))
        T = t_onset + int(rng.integers(3, 18))
    else:
        t_onset = None
        T = int(np.clip(round(rng.lognormal(np.log(cfg.los_median_h), 0.6)), 8, 240))
    t = np.arange(T, dtype=float)

    # --- latent organ-system severities ---------------------------------
    sev = {}
    base = rng.uniform(0.0, 0.35)
    ou = np.empty(T)
    acc = base + rng.normal(0, 0.05)
    for i in range(T):
        acc = acc + 0.15 * (base - acc) + rng.normal(0, 0.06)
        ou[i] = acc
    for c in CHANNELS:
        sev[c] = ou * rng.uniform(0.5, 1.0) + _ar1(rng, T, 0.03)

    # Confounder episodes: short, touch one or two systems, no infection.
    n_conf = rng.poisson(cfg.confounder_rate * T / 36.0)
    for _ in range(n_conf):
        chans = rng.choice(CHANNELS[:3], size=int(rng.integers(1, 3)), replace=False)
        start, dur, amp = rng.uniform(-4, T), rng.uniform(3, 16), rng.uniform(0.3, 1.1)
        for c in chans:
            sev[c] = sev[c] + _bump(t, start, dur, amp)

    # Non-infectious shock in some non-septic patients (hard negatives).
    if not septic and rng.random() < cfg.hidden_shock_rate:
        center, width, amp = rng.uniform(4, T), rng.uniform(1.5, 4), rng.uniform(0.5, 1.1)
        for c, w in (("cardio", 1.0), ("metab", 0.8), ("renal", 0.4), ("resp", 0.3)):
            sev[c] = sev[c] + w * _sigmoid_ramp(t, center, width, amp)

    fever_dir = 1.0
    if septic:
        ramp_len = rng.uniform(4, 24)
        amp = rng.uniform(0.35, 1.2)
        center = t_onset - ramp_len / 2.0
        ramp = _sigmoid_ramp(t, center, ramp_len / 6.0, amp)
        for c in CHANNELS:
            sev[c] = sev[c] + ramp * rng.uniform(0.0, 1.0)
        fever_dir = 1.0 if rng.random() < 0.85 else -1.0
    for c in CHANNELS:
        sev[c] = np.clip(sev[c], -0.3, 2.5)
    overall = np.mean([sev[c] for c in CHANNELS], axis=0)

    # --- vitals -----------------------------------------------------------
    hr0, map0, rr0 = rng.normal(84, 12), rng.normal(82, 9), rng.normal(17, 3)
    t0, pp0 = rng.normal(36.9, 0.3), rng.normal(36, 6)
    v = {}
    v["HR"] = hr0 + 28 * sev["cardio"] + 6 * sev["thermo"] + _ar1(rng, T, 7.0)
    v["MAP"] = map0 - 18 * sev["cardio"] + _ar1(rng, T, 6.0)
    v["SBP"] = v["MAP"] + pp0 - 4 * sev["cardio"] + _ar1(rng, T, 4.0)
    v["DBP"] = v["MAP"] - (v["SBP"] - v["MAP"]) / 2 + _ar1(rng, T, 2.5)
    v["Resp"] = rr0 + 8 * sev["resp"] + 2 * sev["metab"] + _ar1(rng, T, 2.8)
    v["O2Sat"] = np.minimum(98.5 - 5 * sev["resp"] + _ar1(rng, T, 1.0), 100)
    v["Temp"] = t0 + fever_dir * 1.4 * sev["thermo"] + _ar1(rng, T, 0.35)

    # --- labs ---------------------------------------------------------------
    lab = {}
    wbc0, cr0 = rng.normal(9, 2.5), rng.lognormal(np.log(0.9), 0.3)
    bun0, plt0, bili0 = rng.lognormal(np.log(18), 0.35), rng.normal(230, 60), rng.lognormal(np.log(0.7), 0.4)
    hgb0 = rng.normal(10.5, 1.5)
    s_m, s_r, s_c, s_t, s_p = sev["metab"], sev["renal"], sev["coag"], sev["thermo"], sev["resp"]
    lab["WBC"] = wbc0 + 7 * s_t * (1 if fever_dir > 0 else 0.3) + rng.normal(0, 1.2, T)
    lab["Lactate"] = 1.1 + 3.0 * np.maximum(s_m, 0) ** 1.3 + np.abs(rng.normal(0, 0.3, T))
    lab["pH"] = 7.40 - 0.08 * s_m + rng.normal(0, 0.02, T)
    lab["HCO3"] = 24 - 5 * s_m + rng.normal(0, 1.5, T)
    lab["BaseExcess"] = -6 * s_m + rng.normal(0, 1.5, T)
    lab["PaCO2"] = 40 - 5 * s_m + 3 * s_p + rng.normal(0, 3, T)
    lab["Creatinine"] = cr0 * (1 + 0.9 * np.maximum(s_r, 0)) + rng.normal(0, 0.08, T)
    lab["BUN"] = bun0 * (1 + 0.7 * np.maximum(s_r, 0)) + rng.normal(0, 2, T)
    lab["Platelets"] = plt0 * (1 - 0.45 * np.clip(s_c, 0, 1.8)) + rng.normal(0, 10, T)
    lab["Bilirubin_total"] = bili0 * (1 + 1.3 * np.maximum(s_c, 0)) + rng.normal(0, 0.1, T)
    lab["Bilirubin_direct"] = 0.35 * lab["Bilirubin_total"] + rng.normal(0, 0.05, T)
    lab["AST"] = 30 * (1 + 2 * np.maximum(s_c, 0)) * rng.lognormal(0, 0.3, T)
    lab["Alkalinephos"] = 90 * rng.lognormal(0, 0.3, T)
    lab["Glucose"] = 130 + 30 * overall + rng.normal(0, 25, T)
    lab["Potassium"] = 4.1 + 0.3 * s_r + rng.normal(0, 0.4, T)
    lab["Chloride"] = 104 + rng.normal(0, 3, T)
    lab["Calcium"] = 8.5 - 0.3 * s_m + rng.normal(0, 0.5, T)
    lab["Magnesium"] = 2.0 + rng.normal(0, 0.2, T)
    lab["Phosphate"] = 3.5 + 0.5 * s_r + rng.normal(0, 0.6, T)
    lab["Hgb"] = hgb0 + rng.normal(0, 0.4, T)
    lab["Hct"] = 3 * lab["Hgb"] + rng.normal(0, 1, T)
    lab["FiO2"] = np.clip(0.21 + 0.35 * np.clip(s_p, 0, 1.5) + rng.normal(0, 0.05, T), 0.21, 1.0)
    lab["SaO2"] = np.minimum(v["O2Sat"] + rng.normal(0, 1, T), 100)
    lab["PTT"] = 32 * (1 + 0.4 * np.maximum(s_c, 0)) + rng.normal(0, 3, T)
    lab["Fibrinogen"] = 350 * (1 + 0.3 * s_t) + rng.normal(0, 40, T)
    lab["TroponinI"] = 0.02 * rng.lognormal(0, 1.0, T) * (1 + 3 * np.maximum(sev["cardio"] - 1, 0))

    # --- measurement process (informative missingness, site differences) ----
    obs = {}
    vit_p = {"HR": 0.92, "O2Sat": 0.88, "MAP": 0.85, "SBP": 0.80, "Resp": 0.85, "Temp": 0.33,
             "DBP": 0.70 if hospital == 0 else 0.50}
    for name, p in vit_p.items():
        obs[name] = rng.random(T) < p
    lab_base = 0.04 if hospital == 0 else 0.06
    sick = np.clip(overall, 0, 2)
    for lname in LABS:
        obs[lname] = np.zeros(T, dtype=bool)
    for pname, members in PANELS.items():
        p = {"bmp": lab_base + 0.025 * sick, "cbc": lab_base + 0.02 * sick,
             "abg": 0.015 + 0.03 * np.clip(s_p + s_m, 0, 2),
             "lft": 0.01 + 0.02 * sick, "coag": 0.01 + 0.02 * sick,
             "trop": np.full(T, 0.005)}[pname]
        if pname in ("bmp", "cbc"):
            p = np.where(t == 0, 0.75, p)
        draw = rng.random(T) < p
        for m in members:
            obs[m] = obs[m] | (draw & (rng.random(T) > 0.1))
    obs["Lactate"] = obs["Lactate"] | (rng.random(T) < 0.015 + 0.04 * np.clip(s_m, 0, 1.5))

    # --- assemble rows ---------------------------------------------------------
    rows = np.full((T, len(ALL_COLUMNS)), np.nan)
    col = {c: i for i, c in enumerate(ALL_COLUMNS)}
    for name, values in v.items():
        rows[:, col[name]] = np.where(obs[name], np.round(values, 1), np.nan)
    for name, values in lab.items():
        rows[:, col[name]] = np.where(obs[name], np.round(values, 2), np.nan)
    age = float(np.clip(round(rng.normal(63, 16), 0), 18, 95))
    unit_r = rng.random()
    unit1, unit2 = (1.0, 0.0) if unit_r < 0.35 else (0.0, 1.0) if unit_r < 0.7 else (np.nan, np.nan)
    rows[:, col["Age"]] = age
    rows[:, col["Gender"]] = float(rng.random() < 0.55)
    rows[:, col["Unit1"]] = unit1
    rows[:, col["Unit2"]] = unit2
    rows[:, col["HospAdmTime"]] = -round(float(rng.exponential(40)), 2)
    rows[:, col["ICULOS"]] = t + 1
    label = np.zeros(T)
    if septic:
        label[t >= max(t_onset - LABEL_SHIFT_H, 0)] = 1
    rows[:, col["SepsisLabel"]] = label
    meta = {"septic": septic, "t_onset": t_onset, "hospital": "AB"[hospital], "n_hours": T}
    return rows, meta


def _fmt(x: float) -> str:
    if np.isnan(x):
        return "NaN"
    return f"{x:.2f}".rstrip("0").rstrip(".") if x != int(x) else f"{x:.0f}"


def write_psv(path: Path, rows: np.ndarray) -> None:
    lines = ["|".join(ALL_COLUMNS)]
    lines.extend("|".join(_fmt(x) for x in r) for r in rows)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def generate_cohort(out_dir: str | Path, cfg: SynthConfig | None = None) -> dict:
    """Generate ``cfg.n_patients`` PSV files under out_dir/training_set{A,B}."""
    cfg = cfg or SynthConfig()
    out = Path(out_dir)
    for sub in ("training_setA", "training_setB"):
        if (out / sub).exists():
            shutil.rmtree(out / sub)
    rng = np.random.default_rng(cfg.seed)
    manifest = {"source": "synthetic", "generator": "vitalwatch.data.synth",
                "config": asdict(cfg), "patients": {}}
    counters = [0, 0]
    for _ in range(cfg.n_patients):
        hospital = int(rng.random() < cfg.hospital_b_frac)
        counters[hospital] += 1
        pid = f"p{hospital * 100000 + counters[hospital]:06d}"
        rows, meta = generate_patient(rng, cfg, hospital)
        d = out / ("training_setA" if hospital == 0 else "training_setB")
        d.mkdir(parents=True, exist_ok=True)
        write_psv(d / f"{pid}.psv", rows)
        manifest["patients"][pid] = meta
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    n_septic = sum(m["septic"] for m in manifest["patients"].values())
    return {"n_patients": cfg.n_patients, "n_septic": n_septic, "dir": str(out)}


assert len(VALUE_COLUMNS) == 40 and len(ALL_COLUMNS) == 41
