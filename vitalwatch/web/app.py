"""Flask web app: the ward dashboard, Server-Sent Events and a small JSON API."""

from __future__ import annotations

import hmac
import json
import os
import platform
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from ..config import resolve
from ..privacy.audit import verify

HERE = Path(__file__).resolve().parent


def build_runtime(cfg: dict, source: str, log=print) -> dict:
    """Assemble cohort, model, policy, scenario, audit, notes and engine."""
    from ..alerts.policy import PolicyParams
    from ..data.loader import load_cohort_npz
    from ..data.splits import load_splits
    from ..explain.drivers import Explainer
    from ..explain.notes import NoteService, make_backend
    from ..features.offline import build_features
    from ..model.artifacts import read_json
    from ..model.nnpa import detect_nnpa
    from ..model.scorers import load_scorer
    from ..privacy.audit import AuditLog
    from ..privacy.pseudonym import Pseudonymizer, load_or_create_key
    from ..stream.engine import Engine
    from ..stream.hub import Hub
    from ..stream.replay import ReplaySource, WardScenario, build_demo_scenario

    data = resolve(cfg, "data_dir") / "processed"
    art = resolve(cfg, "artifacts_dir")
    sec = resolve(cfg, "secrets_dir")
    cohort = load_cohort_npz(data / f"{source}.npz")
    split = load_splits(data / f"{source}_splits.json")
    meta = read_json(art / "model_meta.json")
    policy = PolicyParams.from_dict(read_json(art / "policy.json"))
    scorer = load_scorer(cfg["scorer"]["kind"], art, calibrated=True)
    log(f"scorer: {scorer.detail}")
    explainer = Explainer(art / "model_xgb.json")

    scen_path = Path(cfg["engine"].get("scenario") or (resolve(cfg, "data_dir").parent / "scenarios" / f"demo_{source}.json"))
    scenario = None
    if scen_path.is_file():
        scenario = WardScenario.from_json(scen_path)
        if scenario.n_beds != cfg["engine"]["n_beds"] or scenario.source != source:
            scenario = None
    if scenario is None:
        def predict(sub):
            return scorer.predict(build_features(sub))
        scenario = build_demo_scenario(cohort, split["test"], predict, policy, n_beds=cfg["engine"]["n_beds"])
        scen_path.parent.mkdir(parents=True, exist_ok=True)
        scenario.to_json(scen_path)
        log(f"demo scenario written to {scen_path}")

    hub = Hub()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    audit_key = load_or_create_key(sec / "audit.key", env="VW_AUDIT_KEY")
    audit = AuditLog(resolve(cfg, "logs_dir") / f"audit_{stamp}.jsonl", audit_key)
    pseudo = Pseudonymizer(load_or_create_key(sec / "pseudonym.key", env="VW_PSEUDO_KEY"))

    env = {"platform": platform.platform(), "python": platform.python_version(),
           "accelerator": detect_nnpa(), "source": source}
    data_note = ("SYNTHETIC patients (VitalWatch generator, PhysioNet layout)" if source == "synthetic"
                 else "PhysioNet 2019 held-out test patients")
    engine_box: dict = {}

    def publish(event: str, payload: dict) -> None:
        hub.publish(event, payload)
        if event == "note_ready" and "engine" in engine_box:
            engine_box["engine"].note_update(payload.get("alert_id"), payload)

    notes = NoteService(make_backend(cfg, log=log), publish, audit,
                        max_tokens=cfg["llm"]["max_tokens"], timeout_s=cfg["llm"]["timeout_s"])
    model_info = {"source": meta.get("source"), "n_trees": meta.get("n_trees"),
                  "spec_hash": meta.get("spec_hash"), "metrics": meta.get("metrics"),
                  "model_sha256": meta.get("model_sha256", "")[:16]}
    engine = Engine(ReplaySource(cohort, scenario), scorer, explainer, policy, notes, hub, audit, pseudo,
                    tick_seconds=cfg["engine"]["tick_seconds"], speed=cfg["engine"]["speed"],
                    env=env, data_note=data_note, model_info=model_info)
    engine_box["engine"] = engine
    audit.append("start", {"app": "vitalwatch", "model_sha256": meta.get("model_sha256"),
                           "spec_hash": meta.get("spec_hash"), "policy": policy.to_dict(),
                           "scorer": scorer.detail, "source": source, "arch": platform.machine()})
    return {"engine": engine, "hub": hub, "audit": audit, "audit_key": audit_key, "notes": notes}


def create_app(rt: dict, token: str | None = None) -> Flask:
    app = Flask(__name__, template_folder=str(HERE / "templates"), static_folder=str(HERE / "static"))
    engine, hub, audit = rt["engine"], rt["hub"], rt["audit"]
    token = token if token is not None else secrets.token_urlsafe(12)
    app.config["VW_TOKEN"] = token

    def authorized() -> bool:
        if not token:
            return True
        given = request.headers.get("X-VW-Token") or (request.get_json(silent=True) or {}).get("token", "")
        return hmac.compare_digest(str(given), token)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True, "sim_h": engine.sim_h})

    @app.get("/stream")
    def stream():
        last = request.headers.get("Last-Event-ID")
        gen = hub.sse(int(last) if last and last.isdigit() else None)
        return Response(gen, mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/state")
    def state():
        return jsonify(engine.snapshot())

    @app.get("/api/bed/<int:bed>")
    def bed(bed: int):
        return jsonify(engine.bed_detail(bed))

    @app.get("/api/metrics")
    def metrics():
        return jsonify(engine.metrics())

    @app.get("/api/env")
    def env():
        return jsonify(engine.env)

    @app.post("/api/ack")
    def ack():
        if not authorized():
            return jsonify({"ok": False, "error": "ward token required"}), 401
        body = request.get_json(force=True, silent=True) or {}
        res = engine.ack(str(body.get("alert_id", "")), str(body.get("user") or "RN on duty"),
                         str(body.get("reason") or "assessed"), int(body.get("snooze_h") or 4))
        return jsonify(res), (200 if res.get("ok") else 409)

    @app.post("/api/control")
    def control():
        if not authorized():
            return jsonify({"ok": False, "error": "ward token required"}), 401
        body = request.get_json(force=True, silent=True) or {}
        return jsonify(engine.control(str(body.get("action", "")), body.get("value")))

    @app.get("/api/audit/verify")
    def audit_verify():
        r = verify(audit.path, rt["audit_key"]).to_dict()
        seq, head = audit.head()
        return jsonify({**r, "head": head[:16], "file": audit.path.name})

    return app


def serve(cfg: dict, source: str, host: str | None = None, port: int | None = None, log=print,
          open_access: bool = False) -> None:
    rt = build_runtime(cfg, source, log=log)
    token = "" if open_access else (cfg["server"].get("token") or os.environ.get("VW_TOKEN") or secrets.token_urlsafe(9))
    app = create_app(rt, token=token)
    stop = threading.Event()
    rt["notes"].start()
    warm = rt["notes"].warmup()
    if warm is not None:
        log(f"Granite warm-up: {warm:.1f}s")
    t = threading.Thread(target=rt["engine"].run, args=(stop,), name="vitalwatch-engine", daemon=True)
    t.start()
    host = host or cfg["server"]["host"]
    port = port or cfg["server"]["port"]
    url = f"http://{'localhost' if host in ('0.0.0.0', '') else host}:{port}/" + (f"?token={token}" if token else "")
    log(f"VitalWatch dashboard: {url}")
    log(json.dumps({"audit_log": str(rt["audit"].path)}))
    try:
        app.run(host=host, port=port, threaded=True, use_reloader=False)
    finally:
        stop.set()
        rt["notes"].stop()
