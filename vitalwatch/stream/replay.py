"""Replay held-out ICU stays into a simulated ward, one hour per tick.

Every patient comes from the held-out test split, so the live demo never shows
a patient the model was trained or tuned on. A scenario places patients into
beds with an admission offset (how many hours of their stay have already
happened when the demo starts); the engine replays those hours silently
first, so trends and sparklines are already populated on screen.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ..alerts.policy import PolicyParams, simulate_fast, threshold_crossings
from ..data.labels import outcomes
from ..data.loader import Cohort


@dataclass
class BedAssignment:
    bed: int
    pid: str
    offset_h: int
    role: str = "background"   # septic_demo | noisy_demo | background


@dataclass
class WardScenario:
    n_beds: int
    assignments: list[BedAssignment]
    queue: list[str] = field(default_factory=list)   # patients admitted when beds free up
    source: str = "synthetic"
    note: str = ""

    def to_json(self, path: str | Path) -> None:
        d = {"n_beds": self.n_beds, "assignments": [asdict(a) for a in self.assignments],
             "queue": self.queue, "source": self.source, "note": self.note}
        Path(path).write_text(json.dumps(d, indent=1), encoding="utf-8")

    @classmethod
    def from_json(cls, path: str | Path) -> "WardScenario":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(d["n_beds"], [BedAssignment(**a) for a in d["assignments"]], d.get("queue", []),
                   d.get("source", "synthetic"), d.get("note", ""))


def build_demo_scenario(cohort: Cohort, test_pids: list[str], predict, policy: PolicyParams,
                        n_beds: int = 24, n_septic: int = 3, seed: int = 2026,
                        first_alert_ticks: tuple[int, ...] = (4, 10, 16)) -> WardScenario:
    """Curate a ward from held-out patients so the 3-minute demo shows alerts.

    ``predict(cohort_subset) -> per-row risk`` is used to find, for septic test
    patients, the hour of VitalWatch's first in-window alert; their offset is
    set so that alert lands a few ticks after the demo starts. Everything else
    is replayed as recorded.
    """
    rng = np.random.default_rng(seed)
    sub = cohort.subset(test_pids)
    outs = {o.pid: o for o in outcomes(sub)}
    risk = predict(sub)
    per = {str(sub.pids[i]): risk[sub.patient_slice(i)] for i in range(sub.n_patients)}

    septic_candidates = []
    noisy_candidates = []
    for pid, o in outs.items():
        r = per[pid]
        alerts = simulate_fast(r, policy)
        if o.septic and not o.poa and o.t_onset is not None and o.t_onset >= 14:
            inwin = [t for t, _ in alerts if o.t_onset - 12 <= t <= o.t_onset + 3]
            early = [t for t, _ in alerts if t < o.t_onset - 12]
            if inwin and not early and inwin[0] >= 8:
                septic_candidates.append((pid, inwin[0]))
        elif not o.septic and o.n_hours >= 30 and not alerts:
            noisy_candidates.append((pid, threshold_crossings(r, policy.theta_off)))

    rng.shuffle(septic_candidates)
    noisy_candidates.sort(key=lambda x: -x[1])
    assignments: list[BedAssignment] = []
    used: set[str] = set()
    beds = list(rng.permutation(n_beds))
    for k, (pid, first_alert) in enumerate(septic_candidates[:n_septic]):
        tick = first_alert_ticks[k % len(first_alert_ticks)]
        assignments.append(BedAssignment(int(beds.pop()), pid, max(first_alert - tick, 0), "septic_demo"))
        used.add(pid)
    if noisy_candidates:
        pid = noisy_candidates[0][0]
        assignments.append(BedAssignment(int(beds.pop()), pid, 6, "noisy_demo"))
        used.add(pid)

    pool = [p for p, o in outs.items() if p not in used and not o.septic and o.n_hours >= 24]
    rng.shuffle(pool)
    while beds and pool:
        pid = pool.pop()
        n = outs[pid].n_hours
        assignments.append(BedAssignment(int(beds.pop()), pid, int(rng.integers(0, max(n - 20, 1))), "background"))
    assignments.sort(key=lambda a: a.bed)
    rest = [p for p in outs if p not in {a.pid for a in assignments}]
    rng.shuffle(rest)
    return WardScenario(n_beds, assignments, rest[:400], cohort.source,
                        note="held-out test patients; offsets chosen so demo alerts appear early")


@dataclass
class BedRow:
    bed: int
    pid: str               # raw dataset id: stays inside the replay source and engine
    hour: int              # hours since this patient's ICU admission
    raw: np.ndarray        # [40] values, no label
    admitted: bool         # first row of a new patient in this bed
    onset_h: float | None  # labelled onset (evaluation overlay only, never used by the model)


class ReplaySource:
    def __init__(self, cohort: Cohort, scenario: WardScenario):
        self.cohort = cohort
        self.scenario = scenario
        self.index = {str(p): i for i, p in enumerate(cohort.pids)}
        self.onset = {o.pid: o.t_onset for o in outcomes(cohort)}
        self.queue = [p for p in scenario.queue if p in self.index]
        self.slots: list[list | None] = [None] * scenario.n_beds   # [pid, next_row, admitted_flag]
        for a in scenario.assignments:
            if a.pid in self.index:
                self.slots[a.bed] = [a.pid, 0, True]
        self.offsets = {a.bed: a.offset_h for a in scenario.assignments}

    def next_hour(self, beds: list[int] | None = None) -> list[BedRow]:
        rows = []
        for b in (beds if beds is not None else range(self.scenario.n_beds)):
            slot = self.slots[b]
            if slot is None:
                if not self.queue:
                    continue
                slot = self.slots[b] = [self.queue.pop(0), 0, True]
            pid, r, admitted = slot
            s = self.cohort.patient_slice(self.index[pid])
            rows.append(BedRow(b, pid, r, self.cohort.values[s.start + r], admitted, self.onset.get(pid)))
            slot[2] = False
            slot[1] = r + 1
            if s.start + r + 1 >= s.stop:  # discharge after this hour
                self.slots[b] = None
        return rows

    def demographics(self, pid: str) -> dict:
        s = self.cohort.patient_slice(self.index[pid])
        from ..schema import COL_INDEX

        v = self.cohort.values[s.start]
        age = v[COL_INDEX["Age"]]
        unit = "MICU" if v[COL_INDEX["Unit1"]] == 1 else "SICU" if v[COL_INDEX["Unit2"]] == 1 else "ICU"
        return {"age": None if np.isnan(age) else float(age), "unit": unit,
                "hours": int(s.stop - s.start)}
