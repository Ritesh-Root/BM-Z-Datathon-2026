"""Rolling per-stage latency statistics (milliseconds)."""

from __future__ import annotations

import threading
from collections import deque

import numpy as np


class LatencyRecorder:
    def __init__(self, maxlen: int = 10_000):
        self._d: dict[str, deque] = {}
        self._maxlen = maxlen
        self._lock = threading.Lock()

    def add(self, stage: str, ms: float) -> None:
        with self._lock:
            self._d.setdefault(stage, deque(maxlen=self._maxlen)).append(ms)

    def summary(self) -> dict:
        with self._lock:
            out = {}
            for k, v in self._d.items():
                if v:
                    a = np.fromiter(v, dtype=float)
                    out[k] = {"p50": round(float(np.percentile(a, 50)), 3),
                              "p99": round(float(np.percentile(a, 99)), 3), "n": len(a)}
            return out
