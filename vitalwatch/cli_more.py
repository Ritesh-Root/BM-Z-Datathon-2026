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


def register(sub) -> None:
    s = sub.add_parser("train", help="train the XGBoost model and export artifacts")
    s.add_argument("--source", choices=["synthetic", "physionet"], default=None)
    s.add_argument("--quick", action="store_true", help="small fast model (demo / CI)")

    s = sub.add_parser("evaluate", help="choose the alert policy on val, report on test vs NEWS2/qSOFA/SIRS")
    s.add_argument("--source", choices=["synthetic", "physionet"], default=None)
    s.add_argument("--target-burden", type=float, default=30.0, help="alerts per 100 patient-days")

    s = sub.add_parser("charts", help="render result charts for the README and deck")
    s.add_argument("--source", choices=["synthetic", "physionet"], default=None)

    s = sub.add_parser("verify-artifacts", help="check golden predictions on this machine")
    s.add_argument("--scorer", default=None, help="xgboost | snapml | snapml-nnpa | snapml-cpu")
    s.add_argument("--atol", type=float, default=1e-5)


COMMANDS = {"train": cmd_train, "verify-artifacts": cmd_verify, "evaluate": cmd_evaluate, "charts": cmd_charts}
