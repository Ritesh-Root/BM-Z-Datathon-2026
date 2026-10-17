from __future__ import annotations

import json

import numpy as np

from vitalwatch.data.labels import LABEL_SHIFT_H, outcomes, summarize
from vitalwatch.data.loader import load_cohort_npz, read_psv, save_cohort_npz
from vitalwatch.data.splits import make_splits
from vitalwatch.data.synth import SynthConfig, generate_cohort
from vitalwatch.schema import ALL_COLUMNS, COL_INDEX, clean_values


def test_psv_layout_matches_physionet(synth_dir):
    f = next((synth_dir / "training_setA").glob("*.psv"))
    df = read_psv(f)
    assert tuple(df.columns) == ALL_COLUMNS
    assert (np.diff(df["ICULOS"].to_numpy()) == 1).all()
    assert "NaN" in f.read_text().splitlines()[1] or df.isna().any().any()


def test_synth_is_deterministic(tmp_path):
    cfg = SynthConfig(n_patients=15, seed=5)
    generate_cohort(tmp_path / "a", cfg)
    generate_cohort(tmp_path / "b", cfg)
    fa = sorted((tmp_path / "a").rglob("*.psv"))
    fb = sorted((tmp_path / "b").rglob("*.psv"))
    assert [p.read_text() for p in fa] == [p.read_text() for p in fb]


def test_labels_match_manifest_onset(synth_dir, cohort):
    manifest = json.loads((synth_dir / "manifest.json").read_text())["patients"]
    outs = {o.pid: o for o in outcomes(cohort)}
    for pid, meta in manifest.items():
        o = outs[pid]
        assert o.septic == meta["septic"]
        if meta["septic"]:
            expected_label = max(meta["t_onset"] - LABEL_SHIFT_H, 0)
            assert o.t_label == expected_label
            if expected_label > 0:
                assert o.t_onset == meta["t_onset"]


def test_summary_rates(cohort):
    s = summarize(outcomes(cohort), cohort.labels)
    assert s["patients"] == 120
    assert 0.1 < s["septic_rate"] < 0.45


def test_npz_roundtrip_and_big_endian(tmp_path, cohort):
    p = tmp_path / "c.npz"
    save_cohort_npz(cohort, p)
    c2 = load_cohort_npz(p)
    assert np.array_equal(cohort.values, c2.values, equal_nan=True)
    assert c2.values.dtype.byteorder in ("=", "<" if np.little_endian else ">")
    # A big-endian copy (as on IBM Z) must convert back to identical native values.
    be = cohort.values.astype(">f8")
    assert np.array_equal(be.astype(np.float64), cohort.values, equal_nan=True)


def test_cohort_subset_and_indices(cohort):
    sub = cohort.subset(list(cohort.pids[:5]))
    assert sub.n_patients == 5
    assert len(sub.values) == sub.offsets[-1]
    r = sub.row_in_patient()
    assert (r[sub.offsets[:-1]] == 0).all()


def test_splits_are_disjoint_and_stratified(cohort):
    outs = outcomes(cohort)
    split = make_splits(outs, seed=1)
    sets = [set(v) for v in split.values()]
    assert not (sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
    assert sum(len(s) for s in sets) == len(outs)
    septic = {o.pid for o in outs if o.septic}
    for name in ("train", "val", "test"):
        assert len(septic & set(split[name])) > 0


def test_clean_values_bounds_and_fio2_percent():
    x = np.full((3, 40), np.nan)
    x[0, COL_INDEX["HR"]] = 400          # implausible
    x[1, COL_INDEX["FiO2"]] = 40         # percent
    x[2, COL_INDEX["Temp"]] = 37.2
    c = clean_values(x)
    assert np.isnan(c[0, COL_INDEX["HR"]])
    assert c[1, COL_INDEX["FiO2"]] == 0.40
    assert c[2, COL_INDEX["Temp"]] == 37.2
    assert x[0, COL_INDEX["HR"]] == 400  # input untouched
