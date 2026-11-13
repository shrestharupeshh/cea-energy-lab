"""Host-side safety envelope. Every setpoint - from a recipe, an operator or a model - passes
through `check_setpoints` before it is sent to a node. The node enforces its own limits again."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Envelope:
    air_t: tuple = (15.0, 32.0)
    rh: tuple = (40.0, 85.0)
    ppfd: tuple = (0.0, 300.0)
    photoperiod_h: tuple = (0.0, 20.0)
    dli_max: float = 17.0                 # mol m-2 d-1 unless the experiment protocol raises it
    max_ppfd_step: float = 100.0          # umol m-2 s-1 per command for model-sourced changes
    max_air_t_step: float = 3.0           # K per command for model-sourced changes
    allow_twin: bool = False              # experiments must opt in to model-driven setpoints


def check_setpoints(new: dict, current: dict | None, env: Envelope, source: str) -> tuple[bool, dict, list[str]]:
    """Validate a setpoint dict {ppfd, photoperiod_h, air_t_day, air_t_night, rh}.

    Returns (accepted, setpoints_to_apply, reasons). Operator and recipe commands that are out of
    range are REJECTED (never silently clamped: the operator must know). Model commands are
    rejected if out of range or if the experiment has not enabled them, and rate-limited."""
    reasons = []
    if source not in ("recipe", "manual", "twin"):
        return False, {}, [f"unknown source {source}"]
    if source == "twin" and not env.allow_twin:
        return False, {}, ["model-driven setpoints are not enabled for this experiment"]
    sp = dict(current or {})
    sp.update(new)
    for key, rng in (("air_t_day", env.air_t), ("air_t_night", env.air_t), ("rh", env.rh), ("ppfd", env.ppfd), ("photoperiod_h", env.photoperiod_h)):
        if key in sp:
            v = sp[key]
            if not isinstance(v, (int, float)) or v != v or not rng[0] <= v <= rng[1]:
                reasons.append(f"{key}={v} outside [{rng[0]}, {rng[1]}]")
    if "ppfd" in sp and "photoperiod_h" in sp and not reasons:
        dli = sp["ppfd"] * sp["photoperiod_h"] * 3600 / 1e6
        if dli > env.dli_max + 1e-9:
            reasons.append(f"DLI {dli:.1f} exceeds limit {env.dli_max}")
    if reasons:
        return False, {}, reasons
    if source == "twin" and current:
        for key, step in (("ppfd", env.max_ppfd_step), ("air_t_day", env.max_air_t_step), ("air_t_night", env.max_air_t_step)):
            if key in sp and key in current and abs(sp[key] - current[key]) > step:
                lim = current[key] + step * (1 if sp[key] > current[key] else -1)
                reasons.append(f"{key} rate-limited to {lim:g}")
                sp[key] = lim
    return True, sp, reasons


def to_node_command(sp: dict, ppfd_full: float, lights_on_min: int = 360, cmd_id: int = 0) -> str:
    """Translate validated setpoints into the node's SET command (duty from the PPFD calibration)."""
    parts = ["SET"]
    if "air_t_day" in sp:
        parts.append(f"air_t_day={sp['air_t_day']:.2f}")
    if "air_t_night" in sp:
        parts.append(f"air_t_night={sp['air_t_night']:.2f}")
    if "rh" in sp:
        parts.append(f"rh={sp['rh']:.1f}")
    if "ppfd" in sp:
        parts.append(f"led={min(sp['ppfd'] / ppfd_full, 1.0):.4f}")
    if "photoperiod_h" in sp:
        parts.append(f"on={lights_on_min}")
        parts.append(f"off={(lights_on_min + int(round(sp['photoperiod_h'] * 60))) % 1440}")
    parts.append(f"id={cmd_id}")
    return " ".join(parts)
