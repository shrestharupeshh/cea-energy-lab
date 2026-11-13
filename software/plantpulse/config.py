"""Repository paths and design-parameter loading."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(os.environ.get("PLANTPULSE_ROOT", Path(__file__).resolve().parents[2]))
DESIGN_PARAMS = REPO_ROOT / "hardware" / "design_parameters.yaml"
DATA_ROOT = Path(os.environ.get("PLANTPULSE_DATA", REPO_ROOT / "experiments"))


@lru_cache(maxsize=4)
def load_design(path: str | None = None) -> dict:
    """Load the hardware design parameters (single source of truth)."""
    with open(path or DESIGN_PARAMS, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
