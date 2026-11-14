"""Imaging schedule: which capture sets are due, and the command sequence for one set."""
from __future__ import annotations

from datetime import datetime, timedelta


def due_times(day_start: datetime, interval_min: int = 120, window_start_min: int = 390, window_end_min: int = 1290) -> list[datetime]:
    """Capture-set start times for one day. The window must lie inside the photoperiod: imaging in
    the dark period would act as a night break."""
    if interval_min < 10:
        raise ValueError("imaging interval below 10 min is not supported (gantry duty, LED blanking)")
    out, m = [], window_start_min
    while m <= window_end_min:
        out.append(day_start + timedelta(minutes=m))
        m += interval_min
    return out


def next_due(now: datetime, last_done: datetime | None, **kw) -> datetime | None:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for t in due_times(day_start, **kw) + due_times(day_start + timedelta(days=1), **kw):
        if (last_done is None or t > last_done) and t >= now - timedelta(minutes=5):
            return t
    return None


def capture_sequence(stereo: bool = True, baseline_mm: float = 60.0) -> list[dict]:
    """Ordered steps for one capture set of a pod: for each station, optional left/right stereo
    offsets then the centre exposure; finally park. Offsets are executed by the node as absolute
    positions (station +/- baseline/2)."""
    steps = []
    for st in (1, 2, 3):
        if stereo:
            steps += [{"station": st, "offset_mm": -baseline_mm / 2, "tag": "L"}, {"station": st, "offset_mm": baseline_mm / 2, "tag": "R"}]
        steps.append({"station": st, "offset_mm": 0.0, "tag": ""})
    steps.append({"station": 0, "offset_mm": 0.0, "tag": "park"})
    return steps


def lights_window_ok(window_start_min: int, window_end_min: int, lights_on_min: int, photoperiod_h: float, margin_min: int = 15) -> bool:
    on, off = lights_on_min + margin_min, lights_on_min + int(photoperiod_h * 60) - margin_min
    return on <= window_start_min and window_end_min <= off
