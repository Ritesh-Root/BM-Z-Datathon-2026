from __future__ import annotations

import numpy as np
import pytest

from vitalwatch.alerts.policy import (ACKED, ALERT, ESCALATED, QUIET, WATCH, BedAlertState, PolicyParams,
                                      acknowledge, raw_params, simulate, simulate_fast, step,
                                      threshold_crossings)


def P(**kw):
    base = dict(theta_on=0.5, theta_off=0.4, sustain_h=2, rise_enabled=False, snooze_h=4,
                breakthrough_delta=0.2, escalate_after_h=2, resolve_after_h=2)
    base.update(kw)
    return PolicyParams(**base)


def test_fast_simulation_matches_reference_state_machine():
    rng = np.random.default_rng(42)
    for _ in range(300):
        n = int(rng.integers(5, 80))
        walk = np.clip(np.cumsum(rng.normal(0, 0.08, n)) + rng.uniform(0, 0.6), 0, 1)
        on = rng.uniform(0.2, 0.8)
        params = PolicyParams(theta_on=on, theta_off=on * rng.choice([0.6, 0.8, 1.0]),
                              sustain_h=int(rng.integers(1, 4)), rise_enabled=bool(rng.random() < 0.5),
                              rise_delta=rng.uniform(0.05, 0.3), rise_window_h=int(rng.integers(1, 5)),
                              snooze_h=int(rng.integers(1, 8)), breakthrough_delta=rng.uniform(0.05, 0.4))
        assert simulate(walk, params) == simulate_fast(walk, params)


def test_sustain_and_hysteresis_prevent_flapping():
    scores = [0.1, 0.55, 0.45, 0.55, 0.45, 0.55, 0.45, 0.55]
    # plain threshold would alarm on every upward crossing
    assert threshold_crossings(scores, 0.5) == 4
    alerts = simulate(scores, P(snooze_h=100))
    assert alerts == [(3, "sustained")]


def test_drop_below_off_resets_watch():
    alerts = simulate([0.6, 0.3, 0.6, 0.3, 0.6], P())
    assert alerts == []


def test_sustain_one_fires_on_threshold():
    assert simulate([0.1, 0.6], P(sustain_h=1)) == [(1, "threshold")]


def test_rise_trigger_fires_immediately():
    assert simulate([0.1, 0.1, 0.45], P(rise_enabled=True, rise_delta=0.3)) == [(2, "rise")]


def test_snooze_suppresses_then_realerts():
    scores = [0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6]
    alerts = simulate(scores, P(snooze_h=4))
    assert alerts == [(1, "sustained"), (5, "re_alert")]


def test_breakthrough_during_snooze():
    scores = [0.6, 0.6, 0.65, 0.9]
    alerts = simulate(scores, P(snooze_h=10, breakthrough_delta=0.2))
    assert alerts == [(1, "sustained"), (3, "breakthrough")]


def test_escalation_and_resolve_without_ack():
    s = BedAlertState()
    params = P(sustain_h=1)
    kinds = []
    for t, p in enumerate([0.6, 0.6, 0.6, 0.3, 0.3]):
        kinds += [(t, e.kind) for e in step(s, t, p, params)]
    assert kinds == [(0, "alert"), (2, "escalation"), (4, "resolve")]
    assert s.state == QUIET


def test_acknowledge_only_from_alert_states():
    s = BedAlertState()
    assert acknowledge(s, 0, 4) is None
    params = P(sustain_h=1)
    step(s, 0, 0.7, params)
    assert s.state == ALERT
    ev = acknowledge(s, 0, 4)
    assert ev.kind == "ack" and s.state == ACKED and s.snooze_until == 4


def test_no_alert_below_threshold_without_rise():
    rng = np.random.default_rng(1)
    scores = rng.uniform(0, 0.49, 500)
    assert simulate(scores, P(sustain_h=1)) == []


def test_raw_params_is_plain_threshold_with_snooze():
    rp = raw_params(0.5, snooze_h=3)
    # the dip at hour 4 happens during the snooze, so it does not re-arm the alarm
    assert simulate([0.6, 0.6, 0.6, 0.6, 0.2, 0.6], rp) == [(0, "threshold"), (3, "re_alert")]
    assert simulate([0.6, 0.2, 0.2, 0.2, 0.6], rp) == [(0, "threshold"), (4, "threshold")]
