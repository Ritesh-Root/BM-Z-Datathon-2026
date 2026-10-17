"""VitalWatch command line: ``python -m vitalwatch <command>``."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path

from .config import ROOT, load_config, resolve


def _data_paths(cfg: dict, source: str) -> dict[str, Path]:
    data = resolve(cfg, "data_dir")
    return {
        "raw": data / ("physionet" if source == "physionet" else "synthetic"),
        "cohort": data / "processed" / f"{source}.npz",
        "splits": data / "processed" / f"{source}_splits.json",
    }


def cmd_doctor(args, cfg) -> int:
    from .model.nnpa import detect_nnpa
    from .explain.notes import resolve_granite_path

    info = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpus": os.cpu_count(),
        "accelerator": detect_nnpa(),
        "granite_model": resolve_granite_path(cfg),
        "artifacts": sorted(p.name for p in resolve(cfg, "artifacts_dir").glob("*") if p.is_file()),
    }
    try:
        import numpy, pandas, xgboost, sklearn  # noqa: F401
        info["versions"] = {"numpy": numpy.__version__, "pandas": pandas.__version__,
                            "xgboost": xgboost.__version__, "scikit-learn": sklearn.__version__}
    except ImportError as exc:  # pragma: no cover
        info["versions"] = {"error": str(exc)}
    print(json.dumps(info, indent=2))
    return 0


def cmd_synth(args, cfg) -> int:
    from .data.synth import SynthConfig, generate_cohort

    out = _data_paths(cfg, "synthetic")["raw"]
    sc = SynthConfig(n_patients=args.n or cfg["synth"]["n_patients"],
                     sepsis_rate=cfg["synth"]["sepsis_rate"], seed=cfg["synth"]["seed"])
    print(json.dumps(generate_cohort(out, sc)))
    return 0


def cmd_ingest(args, cfg) -> int:
    from .data.labels import outcomes, summarize
    from .data.loader import load_psv_tree, save_cohort_npz

    source = args.source or cfg["data"]["source"]
    paths = _data_paths(cfg, source)
    raw = Path(args.raw) if args.raw else paths["raw"]
    cohort = load_psv_tree(raw, limit=args.limit, workers=args.workers, source=source)
    save_cohort_npz(cohort, paths["cohort"])
    summary = summarize(outcomes(cohort), cohort.labels)
    print(json.dumps({"cohort": str(paths["cohort"]), **summary}, indent=2))
    return 0


def cmd_split(args, cfg) -> int:
    from .data.labels import outcomes
    from .data.loader import load_cohort_npz
    from .data.splits import make_splits, save_splits

    source = args.source or cfg["data"]["source"]
    paths = _data_paths(cfg, source)
    cohort = load_cohort_npz(paths["cohort"])
    split = make_splits(outcomes(cohort), seed=cfg["data"]["seed"])
    save_splits(split, paths["splits"])
    print(json.dumps({k: len(v) for k, v in split.items()}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vitalwatch", description=__doc__)
    p.add_argument("--config", default=None, help="path to a TOML config file")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="report platform, IBM Z accelerator and model status")

    s = sub.add_parser("synth", help="generate the synthetic ICU cohort")
    s.add_argument("--n", type=int, default=None)

    s = sub.add_parser("ingest", help="load PSV files into the cohort cache")
    s.add_argument("--source", choices=["synthetic", "physionet"], default=None)
    s.add_argument("--raw", default=None, help="directory holding training_setA/B")
    s.add_argument("--limit", type=int, default=None)
    s.add_argument("--workers", type=int, default=4)

    s = sub.add_parser("split", help="patient-level train/val/test split")
    s.add_argument("--source", choices=["synthetic", "physionet"], default=None)

    from . import cli_more
    cli_more.register(sub)
    return p


COMMANDS = {"doctor": cmd_doctor, "synth": cmd_synth, "ingest": cmd_ingest, "split": cmd_split}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    from . import cli_more
    handler = COMMANDS.get(args.cmd) or cli_more.COMMANDS[args.cmd]
    return int(handler(args, cfg) or 0)


if __name__ == "__main__":
    sys.exit(main())
