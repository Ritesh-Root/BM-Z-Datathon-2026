"""The real-time loop: one tick = one ICU hour for the whole ward.

ingest -> features (all beds, one vectorised call) -> risk (one batched model
call) -> alert policy per bed -> explanation + note + audit for new alerts ->
publish to the dashboard. The language model runs in its own thread, so the
critical decision path is never blocked by text generation.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from ..alerts.policy import (ACKED, ALERT, ESCALATED, QUIET, WATCH, BedAlertState, PolicyParams,
                             acknowledge, step)
from ..explain.drivers import Explainer, top_drivers
from ..explain.notes import NoteFacts, NoteService
from ..features.online import WardFeatureState
from ..features.spec import FEATURE_INDEX
from ..privacy.audit import AuditLog
from ..privacy.pseudonym import Pseudonymizer, age_band
from ..schema import VALUE_COLUMNS
from .hub import Hub
from .latency import LatencyRecorder
from .replay import ReplaySource

log = logging.getLogger("vitalwatch.engine")

TILE_VITALS = (("HR", "HR", "{:.0f}"), ("MAP", "MAP", "{:.0f}"), ("Resp", "RR", "{:.0f}"),
               ("O2Sat", "SpO2", "{:.0f}"), ("Temp", "T", "{:.1f}"))
HISTORY_H = 48


@dataclass
class BedView:
    bed: int
    raw_pid: str = ""
    pseudo: str = ""
    age_band: str = ""
    unit: str = ""
    hour: int = -1
    onset_h: float | None = None
    risk: float | None = None
    hist: deque = field(default_factory=lambda: deque(maxlen=HISTORY_H))   # (sim_h, risk)
    markers: deque = field(default_factory=lambda: deque(maxlen=20))        # (sim_h, kind)
    vitals: dict = field(default_factory=dict)
    last_x: np.ndarray | None = None
    above_shadow: bool = False
    alert: dict | None = None   # latest alert payload for the drawer

    def summary(self, state: BedAlertState, show_gt: bool = True) -> dict:
        return {
            "bed": self.bed + 1, "pid": self.pseudo, "age": self.age_band, "unit": self.unit,
            "hour": self.hour, "risk": None if self.risk is None else round(self.risk, 4),
            "state": state.state, "alert_id": state.alert_id,
            "snooze_left": max(state.snooze_until - self.hour, 0) if state.state == ACKED else None,
            "vitals": self.vitals,
            "gt_onset_in_h": (round(self.onset_h - self.hour, 1) if (show_gt and self.onset_h is not None) else None),
        }


class Engine:
    def __init__(self, source: ReplaySource, scorer, explainer: Explainer, policy: PolicyParams,
                 notes: NoteService, hub: Hub, audit: AuditLog, pseudo: Pseudonymizer,
                 tick_seconds: float = 4.0, speed: float = 1.0, env: dict | None = None,
                 data_note: str = "", model_info: dict | None = None):
        self.source = source
        self.scorer = scorer
        self.explainer = explainer
        self.P = policy
        self.notes = notes
        self.hub = hub
        self.audit = audit
        self.pseudo = pseudo
        self.n_beds = source.scenario.n_beds
        self.features = WardFeatureState(self.n_beds)
        self.states = [BedAlertState() for _ in range(self.n_beds)]
        self.beds = [BedView(b) for b in range(self.n_beds)]
        self.lat = LatencyRecorder()
        self.lock = threading.RLock()
        self.tick_seconds = tick_seconds
        self.speed = speed
        self.paused = False
        self.sim_h = 0
        self.ticks = 0
        self.alert_counter = 0
        self.alerts_fired = 0
        self.shadow_alarms = 0
        self.rows_scored = 0
        self.t_start = time.perf_counter()
        self.env = env or {}
        self.data_note = data_note
        self.model_info = model_info or {}
        self.live = False

    # ------------------------------------------------------------------ helpers

    def _admit(self, b: int, raw_pid: str, onset_h: float | None) -> None:
        self.features.reset(b)
        self.states[b] = BedAlertState()
        demo = self.source.demographics(raw_pid)
        v = self.beds[b] = BedView(b, raw_pid, self.pseudo(raw_pid), age_band(demo["age"]), demo["unit"])
        v.onset_h = onset_h

    def _vitals(self, x: np.ndarray) -> dict:
        out = {}
        for col, label, fmt in TILE_VITALS:
            val = x[FEATURE_INDEX[col]]
            out[label] = None if math.isnan(val) else fmt.format(val)
        return out

    def _facts(self, b: int, trigger: str, drivers: list) -> NoteFacts:
        v = self.beds[b]
        prev = v.hist[-7][1] if len(v.hist) >= 7 else None
        vit = {k: val for k, val in v.vitals.items() if val is not None}
        return NoteFacts(bed=b + 1, pseudo_id=v.pseudo, age_band=v.age_band, unit=v.unit, icu_hour=v.hour,
                         risk_now_pct=round(100 * v.risk, 1),
                         risk_6h_ago_pct=None if prev is None else round(100 * prev, 1),
                         trigger=trigger, drivers=[{"label": d.label, "text": d.text} for d in drivers],
                         vitals=vit)

    def _new_alert_id(self) -> str:
        self.alert_counter += 1
        return f"A-{self.alert_counter:04d}"

    # ------------------------------------------------------------------ tick

    def tick(self, beds: list[int] | None = None, publish: bool = True) -> dict:
        with self.lock:
            t0 = time.perf_counter()
            rows = self.source.next_hour(beds)
            raw = np.full((self.n_beds, len(VALUE_COLUMNS)), np.nan)
            active = np.zeros(self.n_beds, dtype=bool)
            for r in rows:
                if r.admitted:
                    self._admit(r.bed, r.pid, r.onset_h)
                raw[r.bed] = r.raw
                active[r.bed] = True
                self.beds[r.bed].hour = r.hour
            t1 = time.perf_counter()
            X = self.features.update(raw, active)
            t2 = time.perf_counter()
            idx = np.flatnonzero(active)
            risk = self.scorer.predict(X[idx]) if len(idx) else np.zeros(0)
            t3 = time.perf_counter()
            self.rows_scored += len(idx)

            alerts_out = []
            for j, b in enumerate(idx.tolist()):
                v, s = self.beds[b], self.states[b]
                p = float(risk[j])
                v.risk = p
                v.last_x = X[b]
                v.vitals = self._vitals(X[b])
                v.hist.append((self.sim_h, p))
                above = p >= self.P.theta_on
                if above and not v.above_shadow and publish:
                    self.shadow_alarms += 1
                v.above_shadow = above
                for e in step(s, v.hour, p, self.P):
                    if e.kind == "alert":
                        aid = self._new_alert_id()
                        s.alert_id = aid
                        v.markers.append((self.sim_h, "alert"))
                        if not publish:  # history before the demo: acknowledged by the previous shift
                            acknowledge(s, v.hour, self.P.snooze_h)
                            v.markers.append((self.sim_h, "ack"))
                            continue
                        alerts_out.append(self._raise_alert(b, aid, e.trigger, t0))
                    elif publish and e.kind in ("escalation", "resolve"):
                        seq, _ = self.audit.append(e.kind, {"alert_id": e.alert_id, "bed": b + 1, "pid": v.pseudo,
                                                            "risk": round(p, 4)}, sim_h=self.sim_h)
                        v.markers.append((self.sim_h, e.kind))
                        self.hub.publish(e.kind, {"alert_id": e.alert_id, "bed": b + 1, "pid": v.pseudo,
                                                  "sim_h": self.sim_h, "audit_seq": seq})
            t4 = time.perf_counter()
            self.lat.add("ingest", 1e3 * (t1 - t0))
            self.lat.add("features", 1e3 * (t2 - t1))
            self.lat.add("score", 1e3 * (t3 - t2))
            self.lat.add("policy_explain_audit", 1e3 * (t4 - t3))
            self.lat.add("tick_total", 1e3 * (t4 - t0))
            if len(idx):
                self.lat.add("score_per_bed_us", 1e6 * (t3 - t2) / len(idx))
            if publish:
                self.hub.publish("tick", {"sim_h": self.sim_h, "beds": self._tile_list(),
                                          "lat_ms": {"features": round(1e3 * (t2 - t1), 3),
                                                     "score": round(1e3 * (t3 - t2), 3),
                                                     "total": round(1e3 * (t4 - t0), 3)}})
                self.hub.publish("metrics", self.metrics())
            self.sim_h += 1
            self.ticks += 1
            return {"rows": len(idx), "alerts": alerts_out}

    def _raise_alert(self, b: int, aid: str, trigger: str, t0: float) -> dict:
        v = self.beds[b]
        te = time.perf_counter()
        contrib = self.explainer.contributions(v.last_x[None, :])[0]
        drivers = top_drivers(contrib, v.last_x, k=4)
        self.lat.add("explain", 1e3 * (time.perf_counter() - te))
        facts = self._facts(b, trigger, drivers)
        note = self.notes.request(aid, facts)
        payload = {"alert_id": aid, "bed": b + 1, "pid": v.pseudo, "risk": round(v.risk, 4),
                   "trigger": trigger, "drivers": [d.var for d in drivers], "icu_hour": v.hour}
        seq, head = self.audit.append("alert", payload, sim_h=self.sim_h)
        v.alert = {"alert_id": aid, "trigger": trigger, "sim_h": self.sim_h, "risk": round(v.risk, 4),
                   "risk_6h": facts.risk_6h_ago_pct, "drivers": [d.to_dict() for d in drivers],
                   "note": {"source": "template", "text": note}, "audit_seq": seq}
        self.alerts_fired += 1
        e2e = 1e3 * (time.perf_counter() - t0)
        self.lat.add("alert_e2e", e2e)
        out = {**v.alert, "bed": b + 1, "pid": v.pseudo, "latency_ms": round(e2e, 3),
               "llm_pending": self.notes.backend is not None}
        self.hub.publish("alert", out)
        return out

    def _tile_list(self) -> list[dict]:
        return [self.beds[b].summary(self.states[b]) | {"spark": [round(r, 4) for _, r in self.beds[b].hist]}
                for b in range(self.n_beds) if self.beds[b].hour >= 0]

    # ------------------------------------------------------------------ actions

    def ack(self, alert_id: str, user: str, reason: str, snooze_h: int) -> dict:
        with self.lock:
            for b, s in enumerate(self.states):
                if s.alert_id == alert_id and s.state in (ALERT, ESCALATED):
                    v = self.beds[b]
                    acknowledge(s, v.hour, int(snooze_h))
                    v.markers.append((self.sim_h, "ack"))
                    seq, head = self.audit.append("ack", {"alert_id": alert_id, "bed": b + 1, "pid": v.pseudo,
                                                          "by": user[:60], "reason": reason[:120],
                                                          "snooze_h": int(snooze_h)}, sim_h=self.sim_h)
                    out = {"alert_id": alert_id, "bed": b + 1, "by": user[:60], "reason": reason[:120],
                           "snooze_h": int(snooze_h), "audit_seq": seq, "audit_head": head}
                    self.hub.publish("ack", out)
                    return {"ok": True, **out}
            return {"ok": False, "error": "alert is not active (already acknowledged or resolved)"}

    def control(self, action: str, value=None) -> dict:
        with self.lock:
            if action == "pause":
                self.paused = True
            elif action == "resume":
                self.paused = False
            elif action == "speed" and value:
                self.speed = float(min(max(float(value), 0.25), 20.0))
            elif action == "step":
                self.tick()
            self.hub.publish("control", {"paused": self.paused, "speed": self.speed})
            return {"paused": self.paused, "speed": self.speed}

    # ------------------------------------------------------------------ views

    def metrics(self) -> dict:
        lat = self.lat.summary()
        seq, head = self.audit.head()
        elapsed = time.perf_counter() - self.t_start
        return {
            "beds": int(sum(1 for v in self.beds if v.hour >= 0)), "sim_h": self.sim_h, "ticks": self.ticks,
            "latency_ms": lat, "rows_scored": self.rows_scored,
            "rows_per_s_wall": round(self.rows_scored / elapsed, 1) if elapsed > 0 else None,
            "scorer": {"name": getattr(self.scorer, "name", "?"), "device": getattr(self.scorer, "device", "cpu"),
                       "detail": getattr(self.scorer, "detail", "")},
            "llm": {"backend": self.notes.backend.name if self.notes.backend else "template",
                    "queue": self.notes.queue_depth, **self.notes.stats},
            "alerts_fired": self.alerts_fired, "plain_threshold_alarms": self.shadow_alarms,
            "audit": {"seq": seq, "head": head[:16]},
            "paused": self.paused, "speed": self.speed,
        }

    def snapshot(self) -> dict:
        with self.lock:
            beds = []
            for b in range(self.n_beds):
                v = self.beds[b]
                if v.hour < 0:
                    continue
                beds.append(v.summary(self.states[b]) | {
                    "spark": [round(r, 4) for _, r in v.hist],
                    "hist": [[h, round(r, 4)] for h, r in v.hist],
                    "markers": list(v.markers), "alert": v.alert})
            return {"sim_h": self.sim_h, "n_beds": self.n_beds, "beds": beds,
                    "policy": self.P.to_dict(), "metrics": self.metrics(), "env": self.env,
                    "data_note": self.data_note, "model": self.model_info}

    def bed_detail(self, bed_no: int) -> dict:
        b = bed_no - 1
        with self.lock:
            if not (0 <= b < self.n_beds) or self.beds[b].hour < 0:
                return {"error": "no patient in this bed"}
            v = self.beds[b]
            drivers = []
            if v.last_x is not None:
                contrib = self.explainer.contributions(v.last_x[None, :])[0]
                drivers = [d.to_dict() for d in top_drivers(contrib, v.last_x, k=5)]
            return v.summary(self.states[b]) | {
                "hist": [[h, round(r, 4)] for h, r in v.hist], "markers": list(v.markers),
                "alert": v.alert, "drivers_now": drivers, "vitals_24h": self.features.snapshot(b)["vitals_24h"],
                "policy": {"theta_on": self.P.theta_on, "theta_off": self.P.theta_off}}

    def note_update(self, alert_id: str, data: dict) -> None:
        """Called from the note thread so the drawer shows the final note on reload."""
        with self.lock:
            for v in self.beds:
                if v.alert and v.alert.get("alert_id") == alert_id and data.get("valid"):
                    v.alert["note"] = {"source": data.get("source"), "text": data.get("text"),
                                       "gen_s": data.get("gen_s")}

    # ------------------------------------------------------------------ run loop

    def preroll(self) -> None:
        offsets = self.source.offsets
        max_off = max(offsets.values()) if offsets else 0
        self.sim_h = -max_off
        for k in range(max_off):
            beds = [b for b, o in offsets.items() if o >= max_off - k]
            self.tick(beds=beds, publish=False)
        self.sim_h = 0
        self.lat = LatencyRecorder()
        self.t_start = time.perf_counter()
        self.rows_scored = 0
        self.live = True

    def run(self, stop: threading.Event) -> None:
        if not self.live:
            self.preroll()
        while not stop.is_set():
            if not self.paused:
                try:
                    self.tick()
                except Exception as exc:  # keep the ward running; surface the error
                    log.exception("tick failed")
                    self.hub.publish("error", {"message": f"tick failed: {type(exc).__name__}: {exc}"})
            deadline = time.perf_counter() + self.tick_seconds / max(self.speed, 0.01)
            while time.perf_counter() < deadline and not stop.is_set():
                time.sleep(0.05)
