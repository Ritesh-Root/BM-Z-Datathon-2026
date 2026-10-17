"""Additional CLI commands (model, evaluation, serving, benchmarks).

Kept separate from ``__main__`` so heavy imports only happen when needed.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import resolve


def argparse_hidden() -> str:
    return "internal: one benchmark arm in its own process"


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


def _bench_rows(cfg, source: str, n: int = 20000):
    import numpy as np

    from .data.loader import load_cohort_npz
    from .data.splits import load_splits
    from .features.offline import build_features

    p = _paths(cfg, source)
    c = load_cohort_npz(p["cohort"]).subset(load_splits(p["splits"])["test"])
    X = build_features(c)
    rng = np.random.default_rng(0)
    return X[np.sort(rng.choice(len(X), size=min(n, len(X)), replace=False))]


def cmd_bench(args, cfg) -> int:
    from .model.bench import ARMS, run_benchmark

    source = args.source or cfg["data"]["source"]
    arms = args.arms.split(",") if args.arms else ARMS
    r = run_benchmark(resolve(cfg, "artifacts_dir"), _bench_rows(cfg, source), resolve(cfg, "results_dir"),
                      arms=arms, quick=args.quick)
    for a in r["arms"]:
        if a.get("status") == "ok":
            b1 = next((b for b in a["batches"] if b["batch"] == 1), a["batches"][0])
            big = a["batches"][-1]
            print(f"{a['arm']:12s} batch1 p50 {b1['p50_ms']:.3f} ms  p99 {b1['p99_ms']:.3f} ms | "
                  f"batch{big['batch']} {big['rows_per_s']:.0f} rows/s | agree {a.get('agreement_vs_xgboost', {}).get('alert_decisions_identical')}")
        else:
            print(f"{a['arm']:12s} {a.get('status')}: {a.get('reason', '')[:120]}")
    print(r["file"])
    return 0


def cmd_bench_arm(args, cfg) -> int:
    from .model.bench import run_arm

    batches = tuple(int(x) for x in args.batches.split(","))
    r = run_arm(args.arm, resolve(cfg, "artifacts_dir"), Path(args.data), batches=batches,
                min_calls=30 if args.quick else 100, max_seconds=1.0 if args.quick else 3.0)
    print(json.dumps(r))
    return 0


def cmd_loadtest(args, cfg) -> int:
    from .stream.loadtest import run_loadtest

    source = args.source or cfg["data"]["source"]
    beds = tuple(int(x) for x in args.beds.split(","))
    r = run_loadtest(cfg, source, beds_list=beds, hours=args.hours)
    print(r["file"])
    return 0


def cmd_report(args, cfg) -> int:
    from .config import ROOT
    from .evaluation.report import render, update_readme

    ok = update_readme(ROOT / "README.md", resolve(cfg, "results_dir"))
    print("README results section updated" if ok else render(resolve(cfg, "results_dir")))
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

    s = sub.add_parser("bench", help="inference latency/throughput on every available engine (incl. IBM Telum NNPA)")
    s.add_argument("--source", choices=["synthetic", "physionet"], default=None)
    s.add_argument("--arms", default=None, help="comma list; default all")
    s.add_argument("--quick", action="store_true")

    s = sub.add_parser("bench-arm", help=argparse_hidden())
    s.add_argument("arm")
    s.add_argument("--data", required=True)
    s.add_argument("--batches", default="1,8,32,128,512,2048,8192")
    s.add_argument("--quick", action="store_true")

    s = sub.add_parser("loadtest", help="tick latency for 100 to 10,000 beds")
    s.add_argument("--source", choices=["synthetic", "physionet"], default=None)
    s.add_argument("--beds", default="100,1000,5000,10000")
    s.add_argument("--hours", type=int, default=12)

    sub.add_parser("report", help="rewrite the README results section from results/")

    s = sub.add_parser("verify-artifacts", help="check golden predictions on this machine")
    s.add_argument("--scorer", default=None, help="xgboost | snapml | snapml-nnpa | snapml-cpu")
    s.add_argument("--atol", type=float, default=1e-5)


COMMANDS = {"train": cmd_train, "verify-artifacts": cmd_verify, "evaluate": cmd_evaluate, "charts": cmd_charts, "serve": cmd_serve, "demo": cmd_serve, "audit": cmd_audit, "bench": cmd_bench, "bench-arm": cmd_bench_arm, "loadtest": cmd_loadtest, "report": cmd_report}
