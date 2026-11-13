"""Identifier and file naming conventions (documented in docs/architecture/data_architecture.md)."""
from __future__ import annotations

import re
from datetime import datetime, timezone

ID_RE = {
    "experiment": re.compile(r"^EXP-\d{4}-[A-Z0-9]{1,4}$"),
    "unit": re.compile(r"^EXP-\d{4}-[A-Z0-9]{1,4}-P\d{2}$"),
    "plant": re.compile(r"^EXP-\d{4}-[A-Z0-9]{1,4}-P\d{2}-N\d{2}$"),
    "image": re.compile(r"^EXP-\d{4}-[A-Z0-9]{1,4}-P\d{2}-S\d-\d{8}T\d{6}Z(-[LR])?$"),
}


def experiment_id(year: int, code: str) -> str:
    return f"EXP-{year:04d}-{code.upper()}"


def unit_id(exp: str, pod: int) -> str:
    return f"{exp}-P{pod:02d}"


def plant_id(exp: str, pod: int, position: int) -> str:
    return f"{exp}-P{pod:02d}-N{position:02d}"


def utc_stamp(ts: datetime) -> str:
    if ts.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return ts.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def image_id(exp: str, pod: int, station: int, ts: datetime, stereo: str = "") -> str:
    """stereo: '' (station centre), 'L' or 'R' (baseline offsets)."""
    return f"{unit_id(exp, pod)}-S{station}-{utc_stamp(ts)}" + (f"-{stereo}" if stereo else "")


def image_relpath(img_id: str, ext: str = "png") -> str:
    exp = "-".join(img_id.split("-")[:3])
    pod = img_id.split("-")[3]
    day = img_id.split("-")[5][:8]
    return f"{exp}/images/{pod}/{day}/{img_id}.{ext}"


def scan_name(plant: str, ts: datetime) -> str:
    return f"{plant}-SCAN-{utc_stamp(ts)}.png"


def validate(kind: str, value: str) -> bool:
    return bool(ID_RE[kind].match(value))


def plants_at_station(station: int, per_pod: int = 6) -> list[int]:
    """Plant positions visible at a gantry station (1-3). Positions: 1-3 front row, 4-6 back row, by column."""
    if not 1 <= station <= 3:
        raise ValueError("station must be 1..3")
    return [station, station + 3]
