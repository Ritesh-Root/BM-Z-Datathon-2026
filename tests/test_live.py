from __future__ import annotations

import json
import re
import threading
import time

import numpy as np
import pytest

from vitalwatch.alerts.policy import PolicyParams
from vitalwatch.data.labels import outcomes
from vitalwatch.data.splits import make_splits
from vitalwatch.explain.drivers import Explainer
from vitalwatch.explain.notes import NoteFacts, NoteService, StubBackend, template_note, validate_note
from vitalwatch.features.offline import build_features
from vitalwatch.model.scorers import load_scorer
from vitalwatch.model.train_xgb import run_training
from vitalwatch.privacy.audit import AuditLog, tamper_copy, verify
from vitalwatch.privacy.pseudonym import Pseudonymizer, age_band, load_or_create_key
from vitalwatch.stream.engine import Engine
from vitalwatch.stream.hub import Hub
from vitalwatch.stream.replay import ReplaySource, build_demo_scenario

RAW_ID = re.compile(r"\bp\d{6}\b")


# --------------------------------------------------------------------------- privacy

def test_pseudonyms_are_keyed_and_stable(tmp_path):
    k1 = load_or_create_key(tmp_path / "k1")
    assert load_or_create_key(tmp_path / "k1") == k1
    assert oct((tmp_path / "k1").stat().st_mode)[-3:] == "600"
    a, b = Pseudonymizer(k1), Pseudonymizer(load_or_create_key(tmp_path / "k2"))
    assert a("p000123") == a("p000123") != b("p000123")
    ids = {a(f"p{i:06d}") for i in range(40000)}
    assert len(ids) == 40000
    assert age_band(67) == "60-69" and age_band(None) == "age unknown" and age_band(93) == "90+"


def _log(tmp_path, n=5):
    key = b"k" * 32
    log = AuditLog(tmp_path / "a.jsonl", key)
    for i in range(n):
        log.append("alert", {"i": i, "by": "RN"}, sim_h=i)
    return log, key


def test_audit_chain_verifies_and_resumes(tmp_path):
    log, key = _log(tmp_path)
    assert verify(log.path, key).ok
    again = AuditLog(log.path, key)   # reopening continues the same chain
    again.append("ack", {"x": 1})
    r = verify(log.path, key)
    assert r.ok and r.n == 6


def test_audit_detects_edit_delete_reorder_and_wrong_key(tmp_path):
    log, key = _log(tmp_path)
    bad = tamper_copy(log.path, tmp_path / "t.jsonl", 2)
    r = verify(bad, key)
    assert not r.ok and r.first_bad_seq == 2 and "modified" in r.reason
    lines = log.path.read_text().splitlines()
    (tmp_path / "d.jsonl").write_text("\n".join(lines[:1] + lines[2:]) + "\n")
    assert verify(tmp_path / "d.jsonl", key).first_bad_seq == 1
    (tmp_path / "r.jsonl").write_text("\n".join([lines[1], lines[0]] + lines[2:]) + "\n")
    assert verify(tmp_path / "r.jsonl", key).first_bad_seq == 0
    assert not verify(log.path, b"x" * 32).ok


# --------------------------------------------------------------------------- notes

FACTS = NoteFacts(bed=7, pseudo_id="VW-ABC", age_band="60-69", unit="MICU", icu_hour=37, risk_now_pct=18.2,
                  risk_6h_ago_pct=4.1, trigger="sustained",
                  drivers=[{"label": "Respiratory rate", "text": "26 /min, up 8 in 6 h"}],
                  vitals={"HR": "112", "MAP": "64"})


def test_template_note_is_valid_sbar():
    text = template_note(FACTS)
    ok, reason = validate_note(text, FACTS)
    assert ok, reason
    assert text.startswith("S:") and "\nR:" in text


@pytest.mark.parametrize("text,why", [
    ("S: Bed 7 risk 18%.\nB: Resp 26.\nA: Septic shock.\nR: Review.", "disallowed"),
    ("S: Bed 7 risk 18%.\nB: Resp 26.\nA: Concern.\nR: Give vancomycin.", "disallowed"),
    ("S: Bed 7 risk 55%.\nB: Resp 26.\nA: Concern.\nR: Review.", "not in the facts"),
    ("Bed 7 risk 18%. Review now.", "SBAR"),
])
def test_validator_rejects_unsafe_notes(text, why):
    ok, reason = validate_note(text, FACTS)
    assert not ok and why in reason


def test_note_service_never_blocks_and_streams():
    events = []
    good = template_note(FACTS)
    svc = NoteService(StubBackend(good, delay_s=0.01), lambda e, d: events.append((e, d)))
    svc.start()
    t0 = time.perf_counter()
    text = svc.request("A-1", FACTS)
    assert time.perf_counter() - t0 < 0.05 and text == good
    for _ in range(200):
        if any(e == "note_ready" for e, _ in events):
            break
        time.sleep(0.02)
    svc.stop()
    kinds = [e for e, _ in events]
    assert "note_start" in kinds and "note_delta" in kinds and kinds[-1] == "note_ready"
    assert events[-1][1]["valid"] and events[-1][1]["source"] == "stub"


# --------------------------------------------------------------------------- engine + web

@pytest.fixture(scope="module")
def runtime(tmp_path_factory, cohort):
    d = tmp_path_factory.mktemp("live")
    split = make_splits(outcomes(cohort), seed=3)
    run_training(cohort, split, d, d / "eval.npz", quick=True, log=lambda *_: None)
    scorer = load_scorer("xgboost", d, calibrated=True)
    policy = PolicyParams(theta_on=0.05, theta_off=0.03, sustain_h=1)
    scen = build_demo_scenario(cohort, split["test"] + split["val"],
                               lambda sub: scorer.predict(build_features(sub)), policy, n_beds=8)
    hub = Hub()
    audit = AuditLog(d / "audit.jsonl", b"a" * 32)
    slow = StubBackend(lambda m: template_note(FACTS), delay_s=0.25)  # deliberately slow "LLM"
    notes = NoteService(slow, hub.publish, audit)
    notes.start()
    eng = Engine(ReplaySource(cohort, scen), scorer, Explainer(d / "model_xgb.json"), policy, notes, hub,
                 audit, Pseudonymizer(b"p" * 32), tick_seconds=0.01)
    return {"engine": eng, "hub": hub, "audit": audit, "audit_key": b"a" * 32, "notes": notes, "dir": d}


def test_engine_runs_alerts_fast_and_never_leaks_raw_ids(runtime):
    eng, hub = runtime["engine"], runtime["hub"]
    q = hub.subscribe()
    eng.preroll()
    alerts = []
    tick_ms = []
    for _ in range(40):
        t0 = time.perf_counter()
        alerts += eng.tick()["alerts"]
        tick_ms.append(1e3 * (time.perf_counter() - t0))
    assert eng.alerts_fired == len(alerts) > 0
    assert max(tick_ms) < 250, "a tick must not wait for the slow note model"
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    payload = "\n".join(e[2] for e in events) + runtime["audit"].path.read_text()
    assert not RAW_ID.search(payload), "raw dataset id leaked"
    assert verify(runtime["audit"].path, runtime["audit_key"]).ok


def test_ack_changes_state_and_is_audited(runtime):
    eng = runtime["engine"]
    for _ in range(60):
        active = [s.alert_id for s in eng.states if s.state in ("ALERT", "ESCALATED")]
        if active:
            break
        eng.tick()
    assert active, "expected an active alert"
    res = eng.ack(active[0], "RN Test", "assessed", 4)
    assert res["ok"] and res["audit_seq"] >= 0
    assert not eng.ack(active[0], "RN Test", "assessed", 4)["ok"]
    rec = json.loads(runtime["audit"].path.read_text().splitlines()[res["audit_seq"]])
    assert rec["kind"] == "ack" and rec["payload"]["by"] == "RN Test"


def test_web_api_and_token(runtime):
    from vitalwatch.web.app import create_app

    app = create_app(runtime, token="secret")
    c = app.test_client()
    assert c.get("/healthz").json["ok"]
    st = c.get("/api/state").json
    assert st["n_beds"] == 8 and "policy" in st and all(not RAW_ID.search(json.dumps(b)) for b in st["beds"])
    bed = st["beds"][0]["bed"]
    assert "hist" in c.get(f"/api/bed/{bed}").json
    assert c.post("/api/ack", json={"alert_id": "A-9999"}).status_code == 401
    assert c.post("/api/ack", json={"alert_id": "A-9999"}, headers={"X-VW-Token": "secret"}).status_code == 409
    assert c.post("/api/control", json={"action": "pause"}, headers={"X-VW-Token": "secret"}).json["paused"]
    assert c.get("/api/audit/verify").json["ok"]
    assert b"VitalWatch" in c.get("/").data


def test_sse_stream_emits_events(runtime):
    hub = runtime["hub"]
    gen = hub.sse(heartbeat_s=0.2)
    assert next(gen).startswith("retry:")
    threading.Timer(0.05, lambda: hub.publish("tick", {"sim_h": 1, "beds": []})).start()
    chunk = next(gen)
    assert chunk.startswith("id: ") and "event: tick" in chunk
    gen.close()
