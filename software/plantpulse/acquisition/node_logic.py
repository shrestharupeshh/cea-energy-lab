"""Python port of the firmware control core (firmware/node/lib/core). Used by the simulated node
and by the digital twin so that simulated closed-loop behaviour matches the real controller.
Keep the two implementations in step; tests/test_node_logic.py checks the shared behaviours."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

F_OVERTEMP, F_SENSOR_STALE, F_HOST_TIMEOUT, F_LEAK, F_DOOR, F_ESTOP, F_TOPUP_BUDGET, F_FLOAT_HIGH = (1 << i for i in range(8))
FAULT_NAMES = {F_OVERTEMP: "overtemp", F_SENSOR_STALE: "sensor_stale", F_HOST_TIMEOUT: "host_timeout", F_LEAK: "leak",
               F_DOOR: "door", F_ESTOP: "estop", F_TOPUP_BUDGET: "topup_budget", F_FLOAT_HIGH: "float_high"}
SAFE, AUTO, MANUAL = 0, 1, 2


@dataclass
class Limits:
    air_t_min: float = 15.0
    air_t_max: float = 32.0
    air_t_trip: float = 36.0
    rh_min: float = 40.0
    rh_max: float = 85.0
    led_max: float = 1.0
    fan_min: float = 0.15
    comms_timeout_ms: int = 120_000
    sensor_stale_ms: int = 15_000
    topup_max_ms: int = 60_000
    topup_budget_ms_per_h: int = 240_000


@dataclass
class Setpoints:
    air_t_day: float = 23.0
    air_t_night: float = 20.0
    rh: float = 68.0
    led_duty: float = 0.0
    lights_on_min: int = 360
    lights_off_min: int = 1320
    ramp_min: int = 5
    mix_duty: float = 0.30
    pump_on: bool = True


@dataclass
class Inputs:
    air_t: float = math.nan
    rh: float = math.nan
    air_age_ms: int = 0
    door_open: bool = False
    leak: bool = False
    float_low: bool = False
    float_high: bool = False
    estop_ok: bool = True
    host_age_ms: int = 0
    minute_of_day: int = 0


@dataclass
class Outputs:
    heater: float = 0.0
    fan: float = 0.0
    mix: float = 0.0
    led: float = 0.0
    pump: bool = False
    humidifier: bool = False
    topup: bool = False
    gantry_enable: bool = False
    faults: int = 0


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def light_fraction(minute: int, on_min: int, off_min: int, ramp_min: int) -> float:
    if on_min == off_min:
        return 0.0
    since_on = (minute - on_min) % 1440
    length = (off_min - on_min) % 1440
    if since_on >= length:
        return 0.0
    if ramp_min == 0:
        return 1.0
    return clamp(min(since_on / ramp_min, (length - since_on) / ramp_min), 0.0, 1.0)


class PI:
    def __init__(self, kp, ki, lo, hi):
        self.kp, self.ki, self.lo, self.hi, self.i = kp, ki, lo, hi, 0.0

    def update(self, err, dt):
        u = self.kp * err + self.i
        sat = clamp(u, self.lo, self.hi)
        if u == sat or (err > 0 and u < self.lo) or (err < 0 and u > self.hi):
            self.i = clamp(self.i + self.ki * err * dt, self.lo, self.hi)
        return clamp(self.kp * err + self.i, self.lo, self.hi)


@dataclass
class Controller:
    lim: Limits = field(default_factory=Limits)
    sp: Setpoints = field(default_factory=Setpoints)
    mode: int = SAFE
    manual: Outputs = field(default_factory=Outputs)

    def __post_init__(self):
        self._pi = PI(0.35, 0.01, -1.0, 1.0)
        self._humid = False
        self._topup_run = self._topup_hour = self._hour_clock = 0

    def active_air_setpoint(self, minute: int) -> float:
        day = light_fraction(minute, self.sp.lights_on_min, self.sp.lights_off_min, 0) > 0
        return clamp(self.sp.air_t_day if day else self.sp.air_t_night, self.lim.air_t_min, self.lim.air_t_max)

    def step(self, i: Inputs, dt_s: float) -> Outputs:
        L, sp = self.lim, self.sp
        air_valid = not (math.isnan(i.air_t) or math.isnan(i.rh)) and i.air_age_ms < L.sensor_stale_ms
        faults = 0
        faults |= 0 if air_valid else F_SENSOR_STALE
        faults |= F_OVERTEMP if air_valid and i.air_t >= L.air_t_trip else 0
        faults |= F_HOST_TIMEOUT if i.host_age_ms > L.comms_timeout_ms else 0
        faults |= F_LEAK if i.leak else 0
        faults |= F_DOOR if i.door_open else 0
        faults |= 0 if i.estop_ok else F_ESTOP
        faults |= F_FLOAT_HIGH if i.float_high else 0
        dt_ms = int(dt_s * 1000)
        if self.mode == MANUAL:
            o = replace(self.manual)
            o.led, o.heater, o.fan, o.mix = clamp(o.led, 0, L.led_max), clamp(o.heater, 0, 1), clamp(o.fan, 0, 1), clamp(o.mix, 0, 1)
        elif self.mode == AUTO:
            o = Outputs()
            o.led = clamp(sp.led_duty, 0, L.led_max) * light_fraction(i.minute_of_day, sp.lights_on_min, sp.lights_off_min, sp.ramp_min)
            o.mix, o.pump, o.fan = clamp(sp.mix_duty, 0, 1), sp.pump_on, L.fan_min
            if air_valid:
                u = self._pi.update(self.active_air_setpoint(i.minute_of_day) - i.air_t, dt_s)
                if u > 0:
                    o.heater = u
                else:
                    o.fan = L.fan_min + (-u) * (1 - L.fan_min)
                rh_sp = clamp(sp.rh, L.rh_min, L.rh_max)
                if i.rh < rh_sp - 2:
                    self._humid = True
                if i.rh > rh_sp:
                    self._humid = False
                o.humidifier = self._humid
                if i.rh > rh_sp + 5:
                    o.fan = max(o.fan, L.fan_min + clamp((i.rh - rh_sp - 5) / 10, 0, 1) * (1 - L.fan_min))
            else:
                self._pi.i, self._humid = 0.0, False
            self._hour_clock += dt_ms
            if self._hour_clock >= 3_600_000:
                self._hour_clock = self._topup_hour = 0
            want = i.float_low and not i.float_high
            if want and self._topup_run < L.topup_max_ms and self._topup_hour < L.topup_budget_ms_per_h:
                o.topup = True
                self._topup_run += dt_ms
                self._topup_hour += dt_ms
            elif not want:
                self._topup_run = 0
            if self._topup_hour >= L.topup_budget_ms_per_h:
                faults |= F_TOPUP_BUDGET
            o.gantry_enable = True
        else:
            o = Outputs(pump=True, mix=0.3, fan=L.fan_min)
            self._pi.i = 0.0
        o.faults = faults
        if faults & (F_OVERTEMP | F_SENSOR_STALE):
            o.heater = 0.0
        if faults & F_OVERTEMP:
            o.fan, o.led = 1.0, 0.0
        if faults & F_HOST_TIMEOUT:
            o.heater = min(o.heater, 0.5)
        if faults & (F_LEAK | F_FLOAT_HIGH):
            o.pump = o.topup = False
        if faults & F_DOOR:
            o.gantry_enable = False
        if faults & F_ESTOP:
            o.heater = o.led = 0.0
            o.humidifier = o.topup = o.gantry_enable = False
        return o


_SET_KEYS = {"air_t_day": ("air_t_day", "air_t"), "air_t_night": ("air_t_night", "air_t"), "rh": ("rh", "rh"),
             "led": ("led_duty", "led"), "on": ("lights_on_min", "min"), "off": ("lights_off_min", "min"),
             "ramp": ("ramp_min", "ramp"), "mix": ("mix_duty", "unit"), "pump": ("pump_on", "bool")}
_MAN_KEYS = {"heater": "heater", "fan": "fan", "mix": "mix", "led": "led", "pump": "pump", "humid": "humidifier", "topup": "topup"}


def handle_command(line: str, c: Controller) -> dict:
    """Mirror of pp::handle_command. Returns dict(ok, id, msg, move/station, capture, epoch)."""
    r = {"ok": False, "id": -1, "msg": "rejected", "station": None, "capture": False, "epoch": None}
    toks = line.split()
    if not toks:
        r["msg"] = "empty"
        return r
    verb, args = toks[0], toks[1:]
    if verb not in ("SET", "MAN", "MODE", "MOVE", "CAPTURE", "TIME", "PING"):
        r["msg"] = "unknown verb"
        return r
    sp, man, mode, L = replace(c.sp), replace(c.manual), c.mode, c.lim
    station = epoch = None
    for tok in args:
        if verb == "MODE" and "=" not in tok:
            if tok not in ("AUTO", "MANUAL", "SAFE"):
                return r
            mode = {"SAFE": SAFE, "AUTO": AUTO, "MANUAL": MANUAL}[tok]
            continue
        if "=" not in tok:
            return r
        k, _, vs = tok.partition("=")
        try:
            v = float(vs)
        except ValueError:
            return r
        if math.isnan(v):
            return r
        if k == "id":
            r["id"] = int(v)
            continue
        if verb == "SET":
            if k not in _SET_KEYS:
                return r
            attr, kind = _SET_KEYS[k]
            ok = {"air_t": L.air_t_min <= v <= L.air_t_max, "rh": L.rh_min <= v <= L.rh_max, "led": 0 <= v <= L.led_max,
                  "min": 0 <= v < 1440, "ramp": 0 <= v <= 60, "unit": 0 <= v <= 1, "bool": True}[kind]
            if not ok:
                return r
            setattr(sp, attr, (v > 0.5) if kind == "bool" else int(v) if kind in ("min", "ramp") else v)
        elif verb == "MAN":
            if k not in _MAN_KEYS or not 0 <= v <= 1:
                return r
            attr = _MAN_KEYS[k]
            setattr(man, attr, (v > 0.5) if attr in ("pump", "humidifier", "topup") else v)
        elif verb == "MOVE":
            if k != "station" or not 0 <= v <= 3:
                return r
            station = int(v)
        elif verb == "TIME":
            if k != "epoch" or v < 1.6e9:
                return r
            epoch = int(float(vs))
        else:
            return r
    if verb == "SET":
        if (sp.lights_off_min - sp.lights_on_min) % 1440 > 1200:
            r["msg"] = "photoperiod>20h"
            return r
        c.sp = sp
    if verb == "MAN":
        c.manual = man
    if verb == "MODE":
        c.mode = mode
    r.update(ok=True, msg="ok", station=station, capture=verb == "CAPTURE", epoch=epoch)
    return r
