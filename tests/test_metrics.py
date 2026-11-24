from __future__ import annotations

from vitalwatch.evaluation.metrics import aggregate, score_patient


def test_hand_computed_cohort():
    # septic, onset at hour 30 -> detection window [18, 33], evaluated hours 0..33
    a = score_patient([10, 20, 40], True, False, 30.0, 50)   # 10 too early, 20 in window, 40 after end
    assert (a.hours, a.n_alerts, a.n_true, a.lead) == (34, 2, 1, 10.0)
    b = score_patient([35], True, False, 30.0, 50)           # only alert after evaluation end
    assert not b.detected and b.n_alerts == 0
    c = score_patient([32], True, False, 30.0, 50)           # detected 2 h after onset
    assert c.detected and c.lead == -2.0
    d = score_patient([5], False, False, None, 48)           # one false alarm
    e = score_patient([], False, False, None, 48)
    agg = aggregate([a, b, c, d, e])
    assert agg["septic_patients"] == 3
    assert agg["sensitivity"] == round(2 / 3, 4)
    assert agg["sensitivity_early"] == round(1 / 3, 4)
    assert agg["median_lead_h"] == 4.0                       # leads 10 and -2
    assert agg["alerts"] == 4
    assert agg["alerts_per_100_patient_days"] == round(100 * 4 / ((34 * 3 + 96) / 24), 2)
    assert agg["ppv"] == 0.5


def test_present_on_admission_is_reported_separately():
    poa = score_patient([0], True, True, 3.0, 10)
    agg = aggregate([poa])
    assert agg["septic_patients"] == 0 and agg["poa_patients"] == 1 and agg["poa_detected"] == 1.0


def test_paired_bootstrap_compares_policies_on_the_same_patients():
    import numpy as np
    import pytest

    from vitalwatch.evaluation.metrics import bootstrap_hourly_auc, paired_bootstrap

    # 40 septic patients: policy A alerts 5 h before onset in every one, policy B never alerts.
    a = [score_patient([25], True, False, 30.0, 60) for _ in range(40)]
    b = [score_patient([], True, False, 30.0, 60) for _ in range(40)]
    ci = paired_bootstrap(a, b, n=50)
    assert ci["sensitivity_early"] == [1.0, 1.0]          # the difference is 100 points in every resample
    assert ci["alerts_per_100_patient_days"][0] > 0       # A raised alerts, B none
    with pytest.raises(ValueError):
        paired_bootstrap(a, b[:-1])

    # Perfectly separated hourly scores give an AUROC and AUPRC interval of exactly 1.
    ys = [np.array([0, 0, 1]) for _ in range(20)]
    ss = [np.array([0.1, 0.2, 0.9]) for _ in range(20)]
    auc = bootstrap_hourly_auc(ys, ss, n=20)
    assert auc["auroc"] == [1.0, 1.0] and auc["auprc"] == [1.0, 1.0]


def test_bootstrap_reports_ppv_interval():
    from vitalwatch.evaluation.metrics import bootstrap

    res = [score_patient([25], True, False, 30.0, 60) for _ in range(10)] + \
          [score_patient([5], False, False, None, 48) for _ in range(10)]
    ci = bootstrap(res, n=50)
    assert 0.0 < ci["ppv"][0] <= ci["ppv"][1] <= 1.0
