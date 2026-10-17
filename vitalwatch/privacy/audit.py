"""Tamper-evident audit trail for every clinical decision event.

Each record is JSON on its own line, chained to the previous one and sealed
with an HMAC-SHA256 under a secret key:

    mac_n = HMAC(key, canonical(record_n without "mac")), record_n["prev"] = mac_{n-1}

Editing, deleting or reordering any record breaks the chain at that point, and
a forged chain cannot be rebuilt without the key. The current chain head is
shown live on the dashboard as an external anchor.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _mac(key: bytes, record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "mac"}
    return hmac.new(key, canonical(body), hashlib.sha256).hexdigest()


class AuditLog:
    def __init__(self, path: str | Path, key: bytes, fsync: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._key = key
        self._fsync = fsync
        self._lock = threading.Lock()
        self._seq = -1
        self._head = GENESIS
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self._seq, self._head = rec["seq"], rec["mac"]

    def append(self, kind: str, payload: dict, sim_h: float | None = None) -> tuple[int, str]:
        with self._lock:
            rec = {"v": 1, "seq": self._seq + 1, "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                   "sim_h": sim_h, "kind": kind, "payload": payload, "prev": self._head}
            rec["mac"] = _mac(self._key, rec)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n")
                if self._fsync:
                    fh.flush()
                    import os
                    os.fsync(fh.fileno())
            self._seq, self._head = rec["seq"], rec["mac"]
            return self._seq, self._head

    def head(self) -> tuple[int, str]:
        return self._seq, self._head


@dataclass
class VerifyResult:
    ok: bool
    n: int
    first_bad_seq: int | None = None
    reason: str | None = None

    def to_dict(self) -> dict:
        return {"ok": self.ok, "records": self.n, "first_bad_seq": self.first_bad_seq, "reason": self.reason}


def verify(path: str | Path, key: bytes) -> VerifyResult:
    prev = GENESIS
    n = 0
    lines = Path(path).read_text(encoding="utf-8").splitlines() if Path(path).exists() else []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            return VerifyResult(False, n, i, "unreadable record")
        if rec.get("seq") != i:
            return VerifyResult(False, n, i, "sequence gap or reordering")
        if rec.get("prev") != prev:
            return VerifyResult(False, n, i, "broken link to previous record")
        if not hmac.compare_digest(rec.get("mac", ""), _mac(key, rec)):
            return VerifyResult(False, n, i, "record was modified (seal mismatch)")
        prev = rec["mac"]
        n += 1
    return VerifyResult(True, n)


def tamper_copy(src: str | Path, dst: str | Path, seq: int) -> Path:
    """Demo helper: copy the log and silently edit one record's payload."""
    shutil.copy(src, dst)
    lines = Path(dst).read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[seq])
    rec["payload"]["tampered_note"] = "edited after the fact"
    if "by" in rec["payload"]:
        rec["payload"]["by"] = "someone else"
    lines[seq] = json.dumps(rec, sort_keys=True, separators=(",", ":"))
    Path(dst).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return Path(dst)
