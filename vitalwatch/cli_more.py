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


def register(sub) -> None:
    s = sub.add_parser("train", help="train the XGBoost model and export artifacts")
    s.add_argument("--source", choices=["synthetic", "physionet"], default=None)
    s.add_argument("--quick", action="store_true", help="small fast model (demo / CI)")

    s = sub.add_parser("verify-artifacts", help="check golden predictions on this machine")
    s.add_argument("--scorer", default=None, help="xgboost | snapml | snapml-nnpa | snapml-cpu")
    s.add_argument("--atol", type=float, default=1e-5)


COMMANDS = {"train": cmd_train, "verify-artifacts": cmd_verify}
