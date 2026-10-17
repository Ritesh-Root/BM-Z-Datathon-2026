from __future__ import annotations

import numpy as np
import pytest

from vitalwatch.clinical import scores
from vitalwatch.data.loader import Cohort
from vitalwatch.features.offline import build_features, ffill_by_patient
from vitalwatch.features.online import WardFeatureState
from vitalwatch.features.spec import FEATURE_INDEX, FEATURE_NAMES, N_FEATURES, spec_hash
from vitalwatch.schema import COL_INDEX, VALUE_COLUMNS


def _replay_online(c: Cohort, n_beds: int, rng) -> np.ndarray:
    """Replay every patient through the live ward state with random bed
    assignment, staggered admissions and bed turnover. Returns features in
    cohort row order."""
    out = np.full((len(c.values), N_FEATURES), np.nan)
    state = WardFeatureState(n_beds)
    queue = list(rng.permutation(c.n_patients))
    beds: list[tuple[int, int] | None] = [None] * n_beds  # (patient, next row)
    while queue or any(b is not None for b in beds):
        for b in range(n_beds):
            if beds[b] is None and queue and rng.random() < 0.7:
                beds[b] = (queue.pop(), 0)
                state.reset(b)
        raw = np.full((n_beds, len(VALUE_COLUMNS)), np.nan)
        active = np.zeros(n_beds, dtype=bool)
        rows = {}
        for b, slot in enumerate(beds):
            if slot is None:
                continue
            p, r = slot
            s = c.patient_slice(p)
            raw[b] = c.values[s.start + r]
            active[b] = True
            rows[b] = s.start + r
        X = state.update(raw, active)
        for b, row in rows.items():
            out[row] = X[b]
            p, r = beds[b]
            s = c.patient_slice(p)
            beds[b] = (p, r + 1) if s.start + r + 1 < s.stop else None
    return out


def test_feature_spec_shape():
    assert N_FEATURES == 142
    assert len(set(FEATURE_NAMES)) == N_FEATURES
    assert spec_hash() == spec_hash()


def test_online_offline_parity_with_turnover(cohort, rng):
    sub = cohort.subset(list(cohort.pids[:40]))
    offline = build_features(sub, chunk_rows=500)
    online = _replay_online(sub, n_beds=7, rng=rng)
    np.testing.assert_allclose(online, offline, rtol=1e-12, atol=1e-12, equal_nan=True)


def test_causality_truncation(cohort):
    """Features at hour t must not depend on any later hour."""
    full = cohort.subset(list(cohort.pids[:10]))
    X_full = build_features(full)
    for p in range(full.n_patients):
        s = full.patient_slice(p)
        cut = (s.stop - s.start) // 2 + 1
        part = Cohort(full.values[s.start:s.start + cut], full.labels[s.start:s.start + cut],
                      full.pids[p:p + 1], np.array([0, cut]), full.hospital[p:p + 1])
        np.testing.assert_allclose(build_features(part), X_full[s.start:s.start + cut],
                                   rtol=0, atol=0, equal_nan=True)


def test_labels_do_not_change_features(cohort):
    sub = cohort.subset(list(cohort.pids[:15]))
    shuffled = Cohort(sub.values, np.random.default_rng(1).permutation(sub.labels), sub.pids,
                      sub.offsets, sub.hospital)
    np.testing.assert_array_equal(build_features(sub), build_features(shuffled))


def _one_patient(rows: list[dict]) -> Cohort:
    v = np.full((len(rows), len(VALUE_COLUMNS)), np.nan)
    for i, r in enumerate(rows):
        for k, x in r.items():
            v[i, COL_INDEX[k]] = x
    return Cohort(v, np.zeros(len(rows), dtype=np.int8), np.array(["p1"]),
                  np.array([0, len(rows)]), np.array([0], dtype=np.int8))


def test_hand_computed_values():
    rows = [{"HR": 80, "ICULOS": 1}, {"ICULOS": 2}, {"HR": 100, "Lactate": 2.0, "ICULOS": 3},
            {"HR": 110, "ICULOS": 4}, {"HR": 120, "Lactate": 4.0, "Resp": 1000, "ICULOS": 5}]
    X = build_features(_one_patient(rows))
    f = lambda name: X[:, FEATURE_INDEX[name]]  # noqa: E731
    np.testing.assert_array_equal(f("HR"), [80, 80, 100, 110, 120])          # forward-filled
    np.testing.assert_array_equal(f("HR__tsl"), [0, 1, 0, 0, 0])
    assert np.isnan(f("Lactate")[1]) and f("Lactate")[3] == 2.0
    assert np.isnan(f("Resp")[4])                                          # implausible -> NaN
    np.testing.assert_allclose(f("HR__d1")[1:], [0, 20, 10, 10])
    assert np.isnan(f("HR__d1")[0]) and np.isnan(f("HR__d6")[4])
    np.testing.assert_allclose(f("HR__mean6")[4], np.mean([80, 80, 100, 110, 120]))
    np.testing.assert_allclose(f("HR__max24")[4], 120)
    np.testing.assert_allclose(f("HR__slope6")[4], np.polyfit(np.arange(5), [80, 80, 100, 110, 120], 1)[0])
    assert np.isnan(f("HR__slope6")[1])                                    # < 3 points
    np.testing.assert_allclose(f("Lactate__d24")[4], np.nan, equal_nan=True)  # no lactate at admission
    np.testing.assert_array_equal(f("n_labs_24h"), [0, 0, 1, 1, 2])


def test_ffill_respects_patient_boundaries():
    v = np.array([[1.0], [np.nan], [np.nan], [5.0]])
    starts = np.array([0, 0, 2, 2])
    ff, last = ffill_by_patient(v, starts)
    np.testing.assert_array_equal(ff[:, 0], [1, 1, np.nan, 5])
    np.testing.assert_array_equal(last[:, 0], [0, 0, -1, 3])


@pytest.mark.parametrize("rr,expected", [(8, 3), (9, 1), (11, 1), (12, 0), (20, 0), (21, 2), (24, 2), (25, 3)])
def test_news2_resp_table(rr, expected):
    assert scores.news2_resp(np.array([rr], float))[0] == expected


@pytest.mark.parametrize("temp,expected", [(35.0, 3), (35.1, 1), (36.0, 1), (36.1, 0), (38.0, 0), (38.1, 1), (39.0, 1), (39.1, 2)])
def test_news2_temp_table(temp, expected):
    assert scores.news2_temp(np.array([temp]))[0] == expected


@pytest.mark.parametrize("spo2,expected", [(91, 3), (92, 2), (93, 2), (94, 1), (95, 1), (96, 0)])
def test_news2_spo2_table(spo2, expected):
    assert scores.news2_spo2(np.array([spo2], float))[0] == expected


@pytest.mark.parametrize("sbp,expected", [(90, 3), (91, 2), (100, 2), (101, 1), (110, 1), (111, 0), (219, 0), (220, 3)])
def test_news2_sbp_table(sbp, expected):
    assert scores.news2_sbp(np.array([sbp], float))[0] == expected


@pytest.mark.parametrize("hr,expected", [(40, 3), (41, 1), (50, 1), (51, 0), (90, 0), (91, 1), (110, 1), (111, 2), (130, 2), (131, 3)])
def test_news2_hr_table(hr, expected):
    assert scores.news2_hr(np.array([hr], float))[0] == expected


def test_missing_components_score_zero_and_qsofa_sirs():
    nan = np.array([np.nan])
    assert scores.news2_partial(nan, nan, np.array([0.0]), nan, nan, nan)[0] == 0
    assert scores.qsofa_partial(np.array([22.0]), np.array([100.0]))[0] == 2
    assert scores.qsofa_partial(np.array([21.0]), np.array([101.0]))[0] == 0
    assert scores.sirs(np.array([38.5]), np.array([95.0]), np.array([18.0]), np.array([30.0]), np.array([13.0]))[0] == 4
    assert scores.sofa_partial(np.array([40.0]), np.array([2.5]), np.array([65.0]), np.array([3.6]))[0] == 3 + 2 + 1 + 3
