"""Alert policy: turn an hourly risk score into few, early, actionable alerts.

A plain threshold re-alarms whenever the score wobbles around the line, which
is how alarm fatigue starts. This state machine adds:

* sustain     - risk must stay above ``theta_on`` for ``sustain_h`` hours,
* hysteresis  - once watching, small dips above ``theta_off`` do not reset,
* rise        - a sharp rise (``rise_delta`` within ``rise_window_h`` hours)
                alerts immediately, so fast deteriorations are not delayed,
* snooze      - after a nurse acknowledges, the bed stays quiet for
                ``snooze_h`` hours unless risk breaks through
                (``breakthrough_delta`` above the acknowledged level),
* escalation  - an alert left unacknowledged for ``escalate_after_h`` hours
                escalates to the charge nurse,
* resolve     - an unacknowledged alert clears after ``resolve_after_h`` hours
                below ``theta_off`` (it stays in the audit log).

Time is measured in simulated ICU hours (one tick per hour), never in wall
clock, so behaviour is deterministic and testable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

QUIET, WATCH, ALERT, ESCALATED, ACKED = "QUIET", "WATCH", "ALERT", "ESCALATED", "ACKED"


@dataclass(frozen=True)
class PolicyParams:
    theta_on: float
    theta_off: float
    sustain_h: int = 2
    rise_enabled: bool = True
    rise_delta: float = 0.15
    rise_window_h: int = 3
    snooze_h: int = 6
    breakthrough_delta: float = 0.15
    escalate_after_h: int = 2
    resolve_after_h: int = 3

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PolicyParams":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


def raw_params(theta: float, snooze_h: int = 6) -> PolicyParams:
    """A plain threshold with the same snooze: the baseline / ablation policy."""
    return PolicyParams(theta_on=theta, theta_off=theta, sustain_h=1, rise_enabled=False,
                        snooze_h=snooze_h, breakthrough_delta=float("inf"))


@dataclass
class AlertEvent:
    kind: str            # alert | escalation | resolve | ack
    t: int
    score: float
    trigger: str | None = None
    alert_id: str | None = None


@dataclass
class BedAlertState:
    state: str = QUIET
    above: int = 0
    below: int = 0
    hist: list = field(default_factory=list)
    alert_seq: int = 0
    alert_id: str | None = None
    alert_t: int = -1
    unacked_h: int = 0
    ack_score: float = 0.0
    snooze_until: int = -1
    prefix: str = "A"


def _fire(s: BedAlertState, t: int, p: float, trigger: str, events: list) -> None:
    s.state = ALERT
    s.alert_seq += 1
    s.alert_id = f"{s.prefix}-{s.alert_seq}"
    s.alert_t = t
    s.unacked_h = 0
    s.below = 0
    s.above = 0
    events.append(AlertEvent("alert", t, p, trigger, s.alert_id))


def step(s: BedAlertState, t: int, p: float, P: PolicyParams) -> list[AlertEvent]:
    """Advance one hour with score p. Mutates ``s`` and returns emitted events."""
    events: list[AlertEvent] = []
    prev = s.hist
    rise = (P.rise_enabled and len(prev) > 0 and p >= P.theta_off
            and (p - min(prev)) >= P.rise_delta)

    if s.state in (QUIET, WATCH):
        if p >= P.theta_on:
            s.above = 1 if s.state == QUIET else s.above + 1
            if s.above >= P.sustain_h:
                _fire(s, t, p, "threshold" if P.sustain_h <= 1 else "sustained", events)
            elif rise:
                _fire(s, t, p, "rise", events)
            else:
                s.state = WATCH
        elif rise:
            _fire(s, t, p, "rise", events)
        elif p < P.theta_off:
            s.state = QUIET
            s.above = 0
    elif s.state in (ALERT, ESCALATED):
        s.unacked_h += 1
        if s.state == ALERT and P.escalate_after_h > 0 and s.unacked_h >= P.escalate_after_h:
            s.state = ESCALATED
            events.append(AlertEvent("escalation", t, p, None, s.alert_id))
        if p < P.theta_off:
            s.below += 1
            if s.below >= P.resolve_after_h:
                events.append(AlertEvent("resolve", t, p, None, s.alert_id))
                s.state = QUIET
                s.above = 0
                s.below = 0
        else:
            s.below = 0
    elif s.state == ACKED:
        if t < s.snooze_until:
            if p >= P.theta_on and p >= s.ack_score + P.breakthrough_delta:
                _fire(s, t, p, "breakthrough", events)
        elif p >= P.theta_on:
            _fire(s, t, p, "re_alert", events)
        elif p >= P.theta_off:
            s.state = WATCH
            s.above = 0
        else:
            s.state = QUIET
            s.above = 0

    prev.append(p)
    if len(prev) > P.rise_window_h:
        del prev[0]
    return events


def acknowledge(s: BedAlertState, t: int, snooze_h: int) -> AlertEvent | None:
    if s.state not in (ALERT, ESCALATED):
        return None
    s.state = ACKED
    s.snooze_until = t + snooze_h
    s.ack_score = s.hist[-1] if s.hist else 0.0
    return AlertEvent("ack", t, s.ack_score, None, s.alert_id)


def simulate(scores, P: PolicyParams) -> list[tuple[int, str]]:
    """Reference offline simulation: every alert is acknowledged in the same
    hour (so escalation never happens). Returns [(hour, trigger), ...]."""
    s = BedAlertState()
    out = []
    for t, p in enumerate(scores):
        for e in step(s, t, float(p), P):
            if e.kind == "alert":
                out.append((t, e.trigger))
                acknowledge(s, t, P.snooze_h)
    return out


def simulate_fast(scores, P: PolicyParams) -> list[tuple[int, str]]:
    """Same result as ``simulate`` with local variables only (used for the
    policy grid search over thousands of patients). Kept in lock-step with
    ``step`` by a randomized equivalence test."""
    on, off, sus = P.theta_on, P.theta_off, P.sustain_h
    rise_on, rd, rw = P.rise_enabled, P.rise_delta, P.rise_window_h
    snooze, bt = P.snooze_h, P.breakthrough_delta
    state = 0  # 0 quiet, 1 watch, 2 acked
    above = 0
    snooze_until = -1
    ack_score = 0.0
    hist: list[float] = []
    out = []
    for t in range(len(scores)):
        p = float(scores[t])
        rise = rise_on and hist and p >= off and (p - min(hist)) >= rd
        fired = None
        if state != 2:
            if p >= on:
                above = 1 if state == 0 else above + 1
                if above >= sus:
                    fired = "threshold" if sus <= 1 else "sustained"
                elif rise:
                    fired = "rise"
                else:
                    state = 1
            elif rise:
                fired = "rise"
            elif p < off:
                state = 0
                above = 0
        else:
            if t < snooze_until:
                if p >= on and p >= ack_score + bt:
                    fired = "breakthrough"
            elif p >= on:
                fired = "re_alert"
            elif p >= off:
                state = 1
                above = 0
            else:
                state = 0
                above = 0
        hist.append(p)
        if len(hist) > rw:
            del hist[0]
        if fired:
            out.append((t, fired))
            state = 2
            above = 0
            snooze_until = t + snooze
            ack_score = p
    return out


def threshold_crossings(scores, theta: float) -> int:
    """Alarms a plain monitor threshold would raise: every upward crossing."""
    n, was = 0, False
    for p in scores:
        now = p >= theta
        if now and not was:
            n += 1
        was = now
    return n
