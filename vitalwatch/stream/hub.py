"""In-process publish/subscribe hub that feeds Server-Sent Events to browsers."""

from __future__ import annotations

import json
import queue
import threading
from collections import deque
from typing import Iterator

SCHEMA_VERSION = 1


class Hub:
    def __init__(self, ring: int = 200, subscriber_queue: int = 500):
        self._lock = threading.Lock()
        self._subs: list[queue.Queue] = []
        self._ring: deque = deque(maxlen=ring)
        self._next_id = 1
        self._qsize = subscriber_queue
        self.dropped_subscribers = 0

    def publish(self, event: str, data: dict) -> int:
        payload = json.dumps({"v": SCHEMA_VERSION, **data}, separators=(",", ":"), allow_nan=False, default=str)
        with self._lock:
            eid = self._next_id
            self._next_id += 1
            item = (eid, event, payload)
            self._ring.append(item)
            alive = []
            for q in self._subs:
                try:
                    q.put_nowait(item)
                    alive.append(q)
                except queue.Full:
                    self.dropped_subscribers += 1  # too slow: drop it, the browser reconnects
            self._subs = alive
        return eid

    def subscribe(self, last_event_id: int | None = None) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=self._qsize)
        with self._lock:
            if last_event_id is not None:
                for item in self._ring:
                    if item[0] > last_event_id:
                        q.put_nowait(item)
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    @property
    def n_subscribers(self) -> int:
        return len(self._subs)

    def sse(self, last_event_id: int | None = None, heartbeat_s: float = 15.0,
            stop: threading.Event | None = None) -> Iterator[str]:
        q = self.subscribe(last_event_id)
        try:
            yield "retry: 2000\n\n"
            while not (stop and stop.is_set()):
                try:
                    eid, event, payload = q.get(timeout=heartbeat_s)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield f"id: {eid}\nevent: {event}\ndata: {payload}\n\n"
        finally:
            self.unsubscribe(q)
