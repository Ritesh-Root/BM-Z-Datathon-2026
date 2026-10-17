"""Configuration: TOML defaults plus VW_<SECTION>_<KEY> environment overrides."""

from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "configs" / "default.toml"


def _coerce(value: str, like: Any) -> Any:
    if isinstance(like, bool):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(like, int):
        return int(value)
    if isinstance(like, float):
        return float(value)
    return value


def load_config(path: str | os.PathLike | None = None, overrides: dict | None = None) -> dict:
    """Load the config file, apply env overrides, then explicit overrides."""
    with open(path or DEFAULT_CONFIG, "rb") as fh:
        cfg = tomllib.load(fh)
    for section, values in cfg.items():
        if not isinstance(values, dict):
            continue
        for key, current in values.items():
            env = os.environ.get(f"VW_{section.upper()}_{key.upper()}")
            if env is not None:
                values[key] = _coerce(env, current)
    for dotted, value in (overrides or {}).items():
        section, key = dotted.split(".", 1)
        cfg.setdefault(section, {})[key] = value
    return cfg


def resolve(cfg: dict, key: str) -> Path:
    """Absolute path for a [paths] entry (relative paths are repo-relative)."""
    p = Path(cfg["paths"][key])
    return p if p.is_absolute() else ROOT / p


def copy_config(cfg: dict) -> dict:
    return copy.deepcopy(cfg)
