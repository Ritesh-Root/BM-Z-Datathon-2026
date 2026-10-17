"""Additional CLI commands (model, evaluation, serving, benchmarks).

Kept separate from ``__main__`` so heavy imports only happen when needed.
"""

from __future__ import annotations

COMMANDS: dict = {}


def register(sub) -> None:  # noqa: D401 - filled in as modules land
    """Register extra sub-commands on the argparse sub-parser."""
    return None
