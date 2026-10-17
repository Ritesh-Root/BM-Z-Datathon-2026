"""Pseudonymous patient identifiers and minimum-necessary demographics.

Raw dataset identifiers never leave the replay source: the dashboard, the
audit log and the language model only ever see a keyed HMAC pseudonym and an
age band. Without the key, pseudonyms cannot be linked back to records.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path


def load_or_create_key(path: str | Path, env: str | None = None) -> bytes:
    """32-byte secret from an env var (hex) or a 0600 key file (created if missing)."""
    if env and os.environ.get(env):
        return bytes.fromhex(os.environ[env])
    p = Path(path)
    if p.is_file():
        return bytes.fromhex(p.read_text().strip())
    p.parent.mkdir(parents=True, exist_ok=True)
    key = os.urandom(32)
    p.write_text(key.hex())
    os.chmod(p, 0o600)
    return key


class Pseudonymizer:
    def __init__(self, key: bytes):
        self._key = key

    def __call__(self, raw_id: str) -> str:
        digest = hmac.new(self._key, b"pid:" + str(raw_id).encode(), hashlib.sha256).hexdigest()
        return "VW-" + digest[:10].upper()


def age_band(age: float | None) -> str:
    if age is None or age != age:  # NaN
        return "age unknown"
    if age >= 90:
        return "90+"
    lo = int(age // 10) * 10
    return f"{lo}-{lo + 9}"
