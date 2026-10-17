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
