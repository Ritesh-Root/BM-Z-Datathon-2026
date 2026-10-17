"""Additional CLI commands (model, evaluation, serving, benchmarks).

Kept separate from ``__main__`` so heavy imports only happen when needed.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import resolve


def _paths(cfg: dict, source: str) -> dict[str, Path]:
    data = resolve(cfg, "data_dir")
    return {
        "cohort": data / "processed" / f"{source}.npz",
        "splits": data / "processed" / f"{source}_splits.json",
        "eval": data / "processed" / f"{source}_eval.npz",
        "artifacts": resolve(cfg, "artifacts_dir"),
        "results": resolve(cfg, "results_dir"),
    }


def cmd_train(args, cfg) -> int:
    from .data.loader import load_cohort_npz
    from .data.splits import load_splits
    from .model.train_xgb import run_training

    source = args.source or cfg["data"]["source"]
    p = _paths(cfg, source)
    meta = run_training(load_cohort_npz(p["cohort"]), load_splits(p["splits"]),
                        p["artifacts"], p["eval"], quick=args.quick)
    print(json.dumps({k: meta[k] for k in ("n_trees", "train_seconds", "metrics", "spec_hash")}, indent=2))
    return 0


def cmd_verify(args, cfg) -> int:
    from .model.artifacts import check_golden
    from .model.scorers import load_scorer

    art = resolve(cfg, "artifacts_dir")
    report = {}
    kinds = [args.scorer] if args.scorer else ["xgboost", "snapml"]
    ok = True
    for kind in kinds:
        try:
            s = load_scorer(kind, art)
            r = check_golden(s.predict, art / "golden.json", atol=args.atol)
            r["detail"] = getattr(s, "detail", kind)
            ok &= r["ok"]
        except Exception as exc:  # report, do not crash
            r = {"ok": None, "error": f"{type(exc).__name__}: {exc}"}
        report[kind] = r
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


def cmd_evaluate(args, cfg) -> int:
    from .evaluation.evaluate import run_evaluation

    source = args.source or cfg["data"]["source"]
    p = _paths(cfg, source)
    r = run_evaluation(p["eval"], p["results"], p["artifacts"], source, target_burden=args.target_burden)
    sel = r["selected_policy"]
    print(json.dumps({"hourly_test": r["hourly_test"], "policy_test": sel["test"],
                      "alarm_reduction": r["alarm_reduction_test"],
                      "baselines": [{"baseline": b["baseline"], "threshold": b["threshold"],
                                     "baseline_test": {k: b["test"][k] for k in ("sensitivity_early", "alerts_per_100_patient_days", "median_lead_h")},
                                     "vitalwatch_test": {k: b.get("vitalwatch_test", {}).get(k) for k in ("sensitivity_early", "alerts_per_100_patient_days", "median_lead_h")}}
                                    for b in r["baselines_matched_burden"]]}, indent=1))
    return 0


def cmd_charts(args, cfg) -> int:
    from .evaluation.charts import make_all

    source = args.source or cfg["data"]["source"]
    p = _paths(cfg, source)
    print("\n".join(make_all(p["results"], p["artifacts"], p["eval"], source)))
    return 0


def _ensure_pipeline(cfg, source: str, log=print) -> None:
    """Build whatever is missing so a fresh clone can go straight to the dashboard."""
    from .data.labels import outcomes
    from .data.loader import load_cohort_npz, load_psv_tree, save_cohort_npz
    from .data.splits import load_splits, make_splits, save_splits
    from .features.spec import spec_hash
    from .model.artifacts import read_json

    p = _paths(cfg, source)
    if not p["cohort"].exists():
        raw = resolve(cfg, "data_dir") / source
        if source == "synthetic" and not (raw / "training_setA").exists():
            from .data.synth import SynthConfig, generate_cohort
            log("generating synthetic cohort ...")
            generate_cohort(raw, SynthConfig(n_patients=cfg["synth"]["n_patients"],
                                             sepsis_rate=cfg["synth"]["sepsis_rate"], seed=cfg["synth"]["seed"]))
        log("building cohort cache ...")
        save_cohort_npz(load_psv_tree(raw, source=source), p["cohort"])
    if not p["splits"].exists():
        save_splits(make_splits(outcomes(load_cohort_npz(p["cohort"])), seed=cfg["data"]["seed"]), p["splits"])
    meta_path = p["artifacts"] / "model_meta.json"
    stale = (not meta_path.exists() or read_json(meta_path).get("spec_hash") != spec_hash()
             or read_json(meta_path).get("source") != source)
    if stale or not p["eval"].exists():
        from .model.train_xgb import run_training
        log("training model ...")
        run_training(load_cohort_npz(p["cohort"]), load_splits(p["splits"]), p["artifacts"], p["eval"],
                     quick=source == "synthetic", log=log)
    if stale or not (p["artifacts"] / "policy.json").exists() or read_json(p["artifacts"] / "policy.json").get("source") != source:
        from .evaluation.evaluate import run_evaluation
        log("choosing alert policy on validation patients ...")
        run_evaluation(p["eval"], p["results"], p["artifacts"], source, log=log)


def cmd_serve(args, cfg) -> int:
    from .web.app import serve

    source = args.source or cfg["data"]["source"]
    if args.speed:
        cfg["engine"]["speed"] = args.speed
    if args.no_llm:
        cfg["llm"]["backend"] = "off"
    if args.demo:
        _ensure_pipeline(cfg, source)
    serve(cfg, source, host=args.host, port=args.port, open_access=args.open)
    return 0


def cmd_audit(args, cfg) -> int:
    from .privacy.audit import tamper_copy, verify
    from .privacy.pseudonym import load_or_create_key

    key = load_or_create_key(resolve(cfg, "secrets_dir") / "audit.key", env="VW_AUDIT_KEY")
    path = Path(args.file) if args.file else max(resolve(cfg, "logs_dir").glob("audit_*.jsonl"), key=lambda q: q.stat().st_mtime)
    if args.action == "verify":
        r = verify(path, key).to_dict()
        print(json.dumps({"file": str(path), **r}, indent=2))
        return 0 if r["ok"] else 2
    dst = path.with_name(path.stem + f"_tampered_seq{args.seq}.jsonl")
    tamper_copy(path, dst, args.seq)
    r = verify(dst, key).to_dict()
    print(json.dumps({"tampered_copy": str(dst), **r}, indent=2))
    return 0


def register(sub) -> None:
    s = sub.add_parser("train", help="train the XGBoost model and export artifacts")
    s.add_argument("--source", choices=["synthetic", "physionet"], default=None)
    s.add_argument("--quick", action="store_true", help="small fast model (demo / CI)")

    s = sub.add_parser("evaluate", help="choose the alert policy on val, report on test vs NEWS2/qSOFA/SIRS")
    s.add_argument("--source", choices=["synthetic", "physionet"], default=None)
    s.add_argument("--target-burden", type=float, default=30.0, help="alerts per 100 patient-days")

    s = sub.add_parser("charts", help="render result charts for the README and deck")
    s.add_argument("--source", choices=["synthetic", "physionet"], default=None)

    for name, demo in (("serve", False), ("demo", True)):
        s = sub.add_parser(name, help="run the live ward dashboard" + (" (builds anything missing first)" if demo else ""))
        s.add_argument("--source", choices=["synthetic", "physionet"], default=None)
        s.add_argument("--host", default=None)
        s.add_argument("--port", type=int, default=None)
        s.add_argument("--speed", type=float, default=None, help="simulated hours per tick interval multiplier")
        s.add_argument("--no-llm", action="store_true", help="template notes only")
        s.add_argument("--open", action="store_true", help="no ward token (local demos only)")
        s.set_defaults(demo=demo)

    s = sub.add_parser("audit", help="verify the audit chain or make a tampered copy for the demo")
    s.add_argument("action", choices=["verify", "tamper-copy"])
    s.add_argument("--file", default=None, help="audit log (default: newest in logs/)")
    s.add_argument("--seq", type=int, default=2, help="record to tamper with (tamper-copy)")

    s = sub.add_parser("verify-artifacts", help="check golden predictions on this machine")
    s.add_argument("--scorer", default=None, help="xgboost | snapml | snapml-nnpa | snapml-cpu")
    s.add_argument("--atol", type=float, default=1e-5)


COMMANDS = {"train": cmd_train, "verify-artifacts": cmd_verify, "evaluate": cmd_evaluate, "charts": cmd_charts, "serve": cmd_serve, "demo": cmd_serve, "audit": cmd_audit}
