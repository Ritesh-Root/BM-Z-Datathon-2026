"""Nurse handoff notes (SBAR) for alerts.

A deterministic template note is produced instantly for every alert. When the
local IBM Granite model is available (bundled in the IBM LinuxONE JupyterLab
container and run through llama.cpp), a richer note is drafted in the
background and streamed to the dashboard. Patient data never leaves the
machine.
"""

from __future__ import annotations

import glob
import importlib.util
import os
from pathlib import Path


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
