"""Nurse handoff notes (SBAR) for alerts.

A deterministic template note is produced instantly for every alert. When the
local IBM Granite model is available (bundled in the IBM LinuxONE JupyterLab
container and run through llama.cpp with IBM zDNN acceleration), a richer note
is drafted in the background and streamed to the dashboard. The alert itself
never waits for the language model, and patient data never leaves the machine.

Every generated note is checked before it is shown: it must follow the SBAR
layout, stay short, use only numbers present in the facts, and avoid
diagnoses and medication advice. Rejected drafts are logged and the template
note stays on screen.
"""

from __future__ import annotations

import glob
import hashlib
import importlib.util
import json
import os
import queue
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Protocol


def resolve_granite_path(cfg: dict | None = None) -> str | None:
    """Find a local Granite GGUF model without importing IBM's demo package.

    Order: config ``llm.model_path`` -> env ``VW_GRANITE_GGUF`` -> files next to
    the ``loan_demo`` package shipped in the IBM container -> common model dirs.
    """
    candidates: list[str] = []
    if cfg and cfg.get("llm", {}).get("model_path"):
        candidates.append(cfg["llm"]["model_path"])
    if os.environ.get("VW_GRANITE_GGUF"):
        candidates.append(os.environ["VW_GRANITE_GGUF"])
    for c in candidates:
        if c and Path(c).is_file():
            return str(Path(c).resolve())

    found: list[str] = []
    try:
        spec = importlib.util.find_spec("loan_demo")
    except (ImportError, ValueError):
        spec = None
    if spec and spec.submodule_search_locations:
        for loc in spec.submodule_search_locations:
            base = Path(loc)
            for root in (base, base.parent):
                found.extend(glob.glob(str(root / "**" / "*.gguf"), recursive=True))
    for pat in ("~/models/*.gguf", "~/shared/models/*.gguf", "/home/ibm-user/**/*.gguf",
                "/opt/*/models/*.gguf", "/opt/models/*.gguf", "/models/*.gguf"):
        found.extend(glob.glob(os.path.expanduser(pat), recursive=True))
    found = sorted(set(found), key=lambda p: ("granite" not in p.lower(), p))
    return found[0] if found else None


# --------------------------------------------------------------------------- facts


@dataclass
class NoteFacts:
    bed: int
    pseudo_id: str
    age_band: str
    unit: str
    icu_hour: int
    risk_now_pct: float
    risk_6h_ago_pct: float | None
    trigger: str
    drivers: list[dict] = field(default_factory=list)   # [{"label", "text"}]
    vitals: dict = field(default_factory=dict)          # {"HR": "112 bpm", ...}

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


TRIGGER_TEXT = {
    "sustained": "risk stayed above the alert threshold",
    "threshold": "risk crossed the alert threshold",
    "rise": "risk rose sharply",
    "breakthrough": "risk kept rising after the last acknowledgement",
    "re_alert": "risk is still high after the snooze ended",
}


def template_note(f: NoteFacts) -> str:
    prev = f" (was {f.risk_6h_ago_pct:.0f}% 6 h ago)" if f.risk_6h_ago_pct is not None else ""
    drivers = "; ".join(f"{d['label']} {d['text']}" for d in f.drivers[:3]) or "no single dominant signal"
    vit = ", ".join(f"{k} {v}" for k, v in f.vitals.items())
    return (
        f"S: Bed {f.bed} ({f.pseudo_id}, {f.age_band}, {f.unit}), ICU hour {f.icu_hour}. "
        f"VitalWatch sepsis risk {f.risk_now_pct:.0f}%{prev}; {TRIGGER_TEXT.get(f.trigger, f.trigger)}.\n"
        f"B: Strongest contributing signals: {drivers}. Latest vitals: {vit}.\n"
        f"A: Physiological pattern of possible early deterioration. Decision support, not a diagnosis.\n"
        f"R: Bedside review now; follow the unit sepsis screening protocol; acknowledge in VitalWatch."
    )


SYSTEM_PROMPT = (
    "You are a clinical documentation assistant in an intensive care unit. Write a nurse handoff note "
    "in SBAR format using ONLY the facts provided. Do not make a diagnosis. Do not suggest drugs, doses "
    "or specific treatments. Do not invent any value. Use at most 90 words. Output exactly four lines "
    "starting with 'S:', 'B:', 'A:' and 'R:'."
)


def build_messages(f: NoteFacts) -> list[dict]:
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Facts (JSON):\n" + f.to_json()}]


BANNED = re.compile(
    r"\b(diagnos\w*|septic shock|antibiotic\w*|vancomycin|piperacillin|meropenem|ceftriaxone|"
    r"norepinephrine|noradrenaline|vasopressor\w*|mg|mcg|ml/kg|units?/kg|dose\w*|bolus)\b", re.I)
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")


def validate_note(text: str, f: NoteFacts) -> tuple[bool, str]:
    if not all(re.search(rf"(^|\n)\s*{p}:", text) for p in ("S", "B", "A", "R")):
        return False, "missing SBAR sections"
    if len(text.split()) > 120:
        return False, "too long"
    m = BANNED.search(re.sub(r"\bnot an? (medical )?diagnosis\b", "", text, flags=re.I))
    if m:
        return False, f"contains disallowed term '{m.group(0)}'"
    allowed = {float(x) for x in NUMBER.findall(f.to_json())} | {6.0}
    for tok in NUMBER.findall(text):
        v = float(tok)
        decimals = len(tok.split(".")[1]) if "." in tok else 0
        tol = 0.5 * 10 ** (-decimals) + 1e-9   # a fact rounded to the precision shown
        if not any(abs(v - a) <= tol for a in allowed):
            return False, f"number {tok} is not in the facts"
    return True, "ok"


# --------------------------------------------------------------------------- backends


class NoteBackend(Protocol):
    name: str

    def stream(self, messages: list[dict], max_tokens: int) -> Iterator[str]: ...


class StubBackend:
    """Deterministic stand-in used in tests and when no model is available."""

    name = "stub"

    def __init__(self, text_or_fn: str | Callable[[list[dict]], str], delay_s: float = 0.0):
        self.text_or_fn = text_or_fn
        self.delay_s = delay_s

    def stream(self, messages: list[dict], max_tokens: int) -> Iterator[str]:
        text = self.text_or_fn(messages) if callable(self.text_or_fn) else self.text_or_fn
        for tok in re.findall(r"\S+\s*", text):
            if self.delay_s:
                time.sleep(self.delay_s)
            yield tok


class GraniteBackend:
    """IBM Granite (GGUF) through llama.cpp, fully local."""

    name = "granite"

    def __init__(self, model_path: str, n_ctx: int = 2048, n_threads: int | None = None,
                 temperature: float = 0.2):
        from llama_cpp import Llama

        threads = n_threads or max(1, (os.cpu_count() or 2) - 1)
        self.model_path = model_path
        self.temperature = temperature
        self.llm = Llama(model_path=model_path, n_ctx=n_ctx, n_threads=threads, verbose=False)

    def stream(self, messages: list[dict], max_tokens: int) -> Iterator[str]:
        for chunk in self.llm.create_chat_completion(messages=messages, max_tokens=max_tokens,
                                                     temperature=self.temperature, stream=True):
            delta = chunk["choices"][0].get("delta", {}).get("content")
            if delta:
                yield delta


def make_backend(cfg: dict, log=print) -> NoteBackend | None:
    mode = cfg.get("llm", {}).get("backend", "auto")
    if mode in ("off", "template", "none"):
        return None
    path = resolve_granite_path(cfg)
    if not path:
        if mode == "granite":
            raise RuntimeError("Granite model not found; set VW_GRANITE_GGUF")
        log("Granite model not found: using template notes only")
        return None
    try:
        b = GraniteBackend(path, n_ctx=cfg["llm"].get("n_ctx", 2048),
                           temperature=cfg["llm"].get("temperature", 0.2))
        log(f"Granite loaded from {path}")
        return b
    except Exception as exc:  # llama_cpp missing or model incompatible
        if mode == "granite":
            raise
        log(f"Granite unavailable ({exc}); using template notes only")
        return None


# --------------------------------------------------------------------------- service


class NoteService:
    """Drafts notes in a background thread; never blocks the scoring loop."""

    def __init__(self, backend: NoteBackend | None, publish: Callable[[str, dict], None],
                 audit=None, max_tokens: int = 160, timeout_s: float = 90.0, maxsize: int = 8):
        self.backend = backend
        self.publish = publish
        self.audit = audit
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        self.q: queue.Queue = queue.Queue(maxsize=maxsize)
        self._stop = threading.Event()
        self._cancelled: set[str] = set()
        self.stats = {"generated": 0, "rejected": 0, "dropped": 0, "last_tok_s": None, "last_gen_s": None}
        self._thread: threading.Thread | None = None

    @property
    def queue_depth(self) -> int:
        return self.q.qsize()

    def start(self) -> None:
        if self.backend and not self._thread:
            self._thread = threading.Thread(target=self._run, name="vitalwatch-notes", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def cancel(self, alert_id: str) -> None:
        self._cancelled.add(alert_id)

    def request(self, alert_id: str, facts: NoteFacts) -> str:
        """Return the template note now; queue a model draft if a backend exists."""
        text = template_note(facts)
        if self.backend:
            try:
                self.q.put_nowait((alert_id, facts))
            except queue.Full:
                try:
                    self.q.get_nowait()
                    self.stats["dropped"] += 1
                except queue.Empty:
                    pass
                self.q.put_nowait((alert_id, facts))
        return text

    def warmup(self) -> float | None:
        if not self.backend:
            return None
        t0 = time.perf_counter()
        for _ in self.backend.stream([{"role": "user", "content": "Reply with: ready"}], 4):
            pass
        return time.perf_counter() - t0

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                alert_id, facts = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            if alert_id in self._cancelled:
                continue
            self._generate(alert_id, facts)

    def _generate(self, alert_id: str, facts: NoteFacts) -> None:
        t0 = time.perf_counter()
        parts: list[str] = []
        n_tok = 0
        self.publish("note_start", {"alert_id": alert_id, "backend": self.backend.name})
        try:
            for tok in self.backend.stream(build_messages(facts), self.max_tokens):
                parts.append(tok)
                n_tok += 1
                self.publish("note_delta", {"alert_id": alert_id, "delta": tok})
                if alert_id in self._cancelled or time.perf_counter() - t0 > self.timeout_s:
                    break
        except Exception as exc:  # model failure must never take the ward down
            self.publish("note_ready", {"alert_id": alert_id, "source": "template", "valid": False,
                                        "reason": f"model error: {exc}"})
            return
        text = "".join(parts).strip()
        gen_s = time.perf_counter() - t0
        ok, reason = validate_note(text, facts)
        self.stats["last_gen_s"] = round(gen_s, 2)
        self.stats["last_tok_s"] = round(n_tok / gen_s, 2) if gen_s > 0 else None
        digest = hashlib.sha256(text.encode()).hexdigest()
        seq = None
        if self.audit:
            kind = "note_generated" if ok else "note_rejected"
            seq, _ = self.audit.append(kind, {"alert_id": alert_id, "backend": self.backend.name,
                                              "sha256": digest, "reason": reason})
        self.stats["generated" if ok else "rejected"] += 1
        self.publish("note_ready", {"alert_id": alert_id, "source": self.backend.name if ok else "template",
                                    "text": text if ok else None, "valid": ok, "reason": reason,
                                    "gen_s": round(gen_s, 2), "tok_s": self.stats["last_tok_s"],
                                    "audit_seq": seq})
