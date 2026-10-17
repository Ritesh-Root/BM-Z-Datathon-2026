"""Load PhysioNet-layout PSV files into a compact, endian-safe cohort cache."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..schema import ALL_COLUMNS, LABEL, VALUE_COLUMNS


@dataclass
class Cohort:
    """All patients, rows concatenated. Patient p owns rows offsets[p]:offsets[p+1]."""

    values: np.ndarray    # [N, 40] float64, raw (uncleaned) values in VALUE_COLUMNS order
    labels: np.ndarray    # [N] int8 SepsisLabel
    pids: np.ndarray      # [P] str
    offsets: np.ndarray   # [P+1] int64
    hospital: np.ndarray  # [P] int8 (training_setA = 0, training_setB = 1)
    source: str = "unknown"

    @property
    def n_patients(self) -> int:
        return len(self.pids)

    def patient_slice(self, p: int) -> slice:
        return slice(int(self.offsets[p]), int(self.offsets[p + 1]))

    def subset(self, pids: list[str] | set[str]) -> "Cohort":
        want = set(pids)
        idx = [i for i, pid in enumerate(self.pids) if pid in want]
        parts_v, parts_l, offs = [], [], [0]
        for i in idx:
            s = self.patient_slice(i)
            parts_v.append(self.values[s])
            parts_l.append(self.labels[s])
            offs.append(offs[-1] + (s.stop - s.start))
        values = np.concatenate(parts_v) if parts_v else np.zeros((0, len(VALUE_COLUMNS)))
        labels = np.concatenate(parts_l) if parts_l else np.zeros(0, dtype=np.int8)
        return Cohort(values, labels, self.pids[idx], np.asarray(offs, dtype=np.int64),
                      self.hospital[idx], self.source)

    def patient_index(self) -> np.ndarray:
        """[N] patient number for every row."""
        return np.repeat(np.arange(self.n_patients), np.diff(self.offsets))

    def row_in_patient(self) -> np.ndarray:
        """[N] hour index (0-based) of every row within its patient."""
        starts = np.repeat(self.offsets[:-1], np.diff(self.offsets))
        return np.arange(len(self.values)) - starts


def read_psv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="|")
    if tuple(df.columns) != ALL_COLUMNS:
        raise ValueError(f"{path}: unexpected columns {list(df.columns)[:5]}...")
    return df


def _read_one(path: str) -> tuple[str, np.ndarray, np.ndarray]:
    df = read_psv(path)
    arr = df.to_numpy(dtype=np.float64)
    return Path(path).stem, arr[:, :-1], arr[:, -1].astype(np.int8)


def load_psv_tree(root: str | Path, sets: tuple[str, ...] = ("training_setA", "training_setB"),
                  limit: int | None = None, workers: int = 4, source: str = "unknown") -> Cohort:
    root = Path(root)
    files: list[tuple[str, int]] = []
    for h, s in enumerate(sets):
        d = root / s
        if not d.exists():
            # PhysioNet nests the sets under training/
            d = root / "training" / s
        files.extend((str(f), h) for f in sorted(d.glob("*.psv")))
    if limit:
        files = files[:limit]
    if not files:
        raise FileNotFoundError(f"no .psv files under {root}")
    paths = [f for f, _ in files]
    if workers > 1 and len(paths) > 200:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_read_one, paths, chunksize=256))
    else:
        results = [_read_one(p) for p in paths]
    lens = [len(r[1]) for r in results]
    offsets = np.zeros(len(results) + 1, dtype=np.int64)
    offsets[1:] = np.cumsum(lens)
    return Cohort(
        values=np.concatenate([r[1] for r in results]),
        labels=np.concatenate([r[2] for r in results]),
        pids=np.array([r[0] for r in results]),
        offsets=offsets,
        hospital=np.array([h for _, h in files], dtype=np.int8),
        source=source,
    )


def save_cohort_npz(c: Cohort, path: str | Path) -> None:
    """Explicit little-endian dtypes and no pickles, so the cache is portable
    between x86 (little-endian) and IBM Z (big-endian)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        values=c.values.astype("<f8"),
        labels=c.labels.astype("<i1"),
        offsets=c.offsets.astype("<i8"),
        hospital=c.hospital.astype("<i1"),
    )
    path.with_suffix(".json").write_text(
        json.dumps({"pids": [str(p) for p in c.pids], "source": c.source,
                    "columns": list(VALUE_COLUMNS), "label": LABEL}), encoding="utf-8")


def load_cohort_npz(path: str | Path) -> Cohort:
    path = Path(path)
    with np.load(path, allow_pickle=False) as z:
        values = z["values"].astype(np.float64)    # converts to native byte order
        labels = z["labels"].astype(np.int8)
        offsets = z["offsets"].astype(np.int64)
        hospital = z["hospital"].astype(np.int8)
    meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    if meta["columns"] != list(VALUE_COLUMNS):
        raise ValueError("cohort cache column layout does not match this version")
    return Cohort(values, labels, np.array(meta["pids"]), offsets, hospital, meta.get("source", "unknown"))
