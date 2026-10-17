"""Patient-level train / validation / test split, stratified by outcome and site."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .labels import Outcome


def make_splits(outs: list[Outcome], seed: int = 2026,
                frac: tuple[float, float, float] = (0.70, 0.15, 0.15)) -> dict[str, list[str]]:
    rng = np.random.default_rng(seed)
    strata: dict[tuple[bool, int], list[str]] = {}
    for o in outs:
        strata.setdefault((o.septic, o.hospital), []).append(o.pid)
    split = {"train": [], "val": [], "test": []}
    for key in sorted(strata):
        pids = np.array(sorted(strata[key]))
        rng.shuffle(pids)
        n = len(pids)
        n_tr = int(round(frac[0] * n))
        n_va = int(round(frac[1] * n))
        split["train"].extend(pids[:n_tr].tolist())
        split["val"].extend(pids[n_tr:n_tr + n_va].tolist())
        split["test"].extend(pids[n_tr + n_va:].tolist())
    for k in split:
        split[k] = sorted(split[k])
    return split


def save_splits(split: dict, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(split), encoding="utf-8")


def load_splits(path: str | Path) -> dict[str, list[str]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
