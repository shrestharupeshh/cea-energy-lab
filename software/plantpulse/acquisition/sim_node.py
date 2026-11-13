"""Simulated pod node. Speaks the serial protocol of firmware/PROTOCOL.md, runs the same control
logic as the firmware, and drives the digital-twin environment model with sensor noise.

Used for: host-software tests without hardware, operator training, and the virtual laboratory.
Everything it emits is SIMULATED and must only ever be stored under an experiment whose
data_class is 'simulated'.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import numpy as np

from ..digital_twin import crop as cropm
from ..digital_twin import environment as envm
from . import node_logic as nlg


@dataclass
class SensorNoise:
    air_t: float = 0.03
    rh: float = 0.3
    co2: float = 8.0
    sol_t: float = 0.03
    ph: float = 0.01
    ec: float = 6.0
    res_counts: float = 40.0
    par_rel: float = 0.01
    power_rel: float = 0.003


@dataclass
class SimNode:
    pod: int = 1
    seed: int = 0
    env: envm.EnvParams = field(default_factory=envm.EnvParams.from_design)
    crop: cropm.CropParams = field(default_factory=cropm.CropParams)
    noise: SensorNoise = field(default_factory=SensorNoise)
    room_t: float = 20.0
    room_rh: float = 50.0
    room_co2: float = 420.0
    ec_ms: float = 1.4
    growth_multiplier: float = 1.0
    init_shoot_dw: float = 0.06
    # calibration constants of the simulated transducers (the host must recover engineering units)
    par_counts_per_umol: float = 41.0
    res_counts_per_g: float = 430.0
    res_zero_counts: float = 12000.0

    def __post_init__(self):
        self.rng = np.random.default_rng(self.seed)
        self.ctl = nlg.Controller()
        self.state = envm.EnvState(air_t=self.room_t + 0.5, w=float(envm.abs_hum(self.room_t + 0.5, 55.0)), co2=self.room_co2, sol_t=self.room_t)
        cs = cropm.CropState.from_seedling(self.init_shoot_dw, self.crop)
        self.xn, self.xs = cs.x_nsdw, cs.x_sdw
        self.ms = 0
        self.seq = 0
        self.epoch = None
        self.host_age_ms = 0
        self.led_wh = self.act_wh = 0.0
        self.reservoir_g = 5000.0
        self.tub_deficit_g = 0.0
        self.ph = 5.8
        self.gpos = 0
        self.door_open = self.leak = False
        self.out_lines: list[str] = [json.dumps({"t": "H", "pod": self.pod, "fw": "sim-0.1.0", "sim": True})]
        self.last_outputs = nlg.Outputs()

    # ------------------------------------------------------------------ protocol
    def write(self, line: str):
        r = nlg.handle_command(line.strip(), self.ctl)
        if r["ok"]:
            self.host_age_ms = 0
            if r["epoch"] is not None:
                self.epoch = (r["epoch"], self.ms)
            if r["station"] is not None:
                self.gpos = int(round(([40, 200, 400, 600][r["station"]] - 20) * 80))
            if r["capture"]:
                self.out_lines.append(json.dumps({"t": "E", "ev": "capture_done", "ms": self.ms, "pos": self.gpos}))
        self.out_lines.append(json.dumps({"t": "A", "id": r["id"], "ok": r["ok"], "msg": r["msg"]}))

    def readlines(self) -> list[str]:
        out, self.out_lines = self.out_lines, []
        return out

    def minute_of_day(self) -> int:
        if self.epoch is None:
            return 0
        return int(((self.epoch[0] + (self.ms - self.epoch[1]) / 1000) % 86400) // 60)

    # ------------------------------------------------------------------ physics + control
    def step(self, dt_s: float = 1.0, emit: bool = True) -> dict:
        n = self.noise
        self.ms += int(dt_s * 1000)
        self.host_age_ms += int(dt_s * 1000)
        meas_t = self.state.air_t + self.rng.normal(0, n.air_t)
        meas_rh = float(np.clip(self.state.rh + self.rng.normal(0, n.rh), 0, 100))
        if self.door_open:                                   # door open: air mixes with the room
            self.state.air_t += (self.room_t - self.state.air_t) * min(dt_s / 60.0, 1.0)
        sp = self.ctl.sp
        if self.epoch is None:
            saved = (sp.lights_on_min, sp.lights_off_min)
            sp.lights_off_min = sp.lights_on_min
        o = self.ctl.step(nlg.Inputs(air_t=meas_t, rh=meas_rh, air_age_ms=int(dt_s * 1000), host_age_ms=self.host_age_ms,
                                     minute_of_day=self.minute_of_day(), door_open=self.door_open, leak=self.leak,
                                     float_low=self.tub_deficit_g > 150.0), dt_s)
        if self.epoch is None:
            sp.lights_on_min, sp.lights_off_min = saved
        self.last_outputs = o
        u = envm.Actuators(led=o.led, heater=o.heater, fan=o.fan, mix=o.mix, humidifier=o.humidifier, pump=o.pump)
        ppfd = o.led * self.env.ppfd_full
        par = ppfd / cropm.UMOL_PER_J
        dn, ds = cropm.derivatives(self.xn, self.xs, par, self.state.co2, self.state.air_t, self.crop, self.ec_ms)
        f_phot = float(cropm.gross_photosynthesis(self.xs, par, self.state.co2, self.state.air_t, self.crop, self.ec_ms))
        transp = float(cropm.transpiration(self.xs + self.xn, par, self.state.air_t, self.state.rh, self.crop)) * self.env.grow_area_m2
        self.xn = max(self.xn + dt_s * dn * self.growth_multiplier, 0.0)
        self.xs = max(self.xs + dt_s * ds * self.growth_multiplier, 1e-9)
        self.state = envm.step(self.state, u, self.env, dt_s, self.room_t, self.room_rh, self.room_co2, transp,
                               0.8 * f_phot * self.env.grow_area_m2 * self.growth_multiplier)
        pw = envm.power_w(u, self.env)
        led_w = pw["led_w"] * (1 + self.rng.normal(0, n.power_rel))
        act_w = (pw["heater_w"] + pw["fan_w"] + pw["pump_w"] + pw["humid_w"]) * (1 + self.rng.normal(0, n.power_rel))
        self.led_wh += led_w * dt_s / 3600
        self.act_wh += act_w * dt_s / 3600
        # water: transpiration lowers the tub level; the peristaltic pump refills from the reservoir (1.2 g/s)
        self.tub_deficit_g += transp * dt_s
        if o.topup and self.reservoir_g > 0:
            moved = min(1.2 * dt_s, self.reservoir_g)
            self.reservoir_g -= moved
            self.tub_deficit_g -= moved
        self.ph += 0.02 * dt_s / 86400 * (1 + 5 * f_phot * 1e3) + self.rng.normal(0, 1e-5)      # slow upward drift
        frame = {
            "t": "S", "pod": self.pod, "seq": self.seq, "ms": self.ms, "mode": self.ctl.mode, "faults": o.faults,
            "air_t": round(meas_t, 3), "rh": round(meas_rh, 2), "co2": round(self.state.co2 + self.rng.normal(0, n.co2)),
            "par_raw": round(max(ppfd * self.par_counts_per_umol * (1 + self.rng.normal(0, n.par_rel)), 0)),
            "sol_t": round(self.state.sol_t + self.rng.normal(0, n.sol_t), 3), "sol_t2": math.nan,
            "ph": round(self.ph + self.rng.normal(0, n.ph), 3), "ec": round(self.ec_ms * 1000 + self.rng.normal(0, n.ec), 1),
            "res_raw": round(self.res_zero_counts + self.reservoir_g * self.res_counts_per_g + self.rng.normal(0, n.res_counts)),
            "flow_hz": round(55.0 + self.rng.normal(0, 1.0), 1) if o.pump else 0.0, "tach0_hz": round(73 * o.fan, 1), "tach1_hz": round(73 * o.mix, 1),
            "led_w": round(led_w, 3), "act_w": round(act_w, 3), "led_wh": round(self.led_wh, 4), "act_wh": round(self.act_wh, 4),
            "u_heat": round(o.heater, 3), "u_fan": round(o.fan, 3), "u_mix": round(o.mix, 3), "u_led": round(o.led, 3),
            "pump": int(o.pump), "humid": int(o.humidifier), "topup": int(o.topup), "door": int(self.door_open), "leak": int(self.leak),
            "flo": int(self.tub_deficit_g > 150.0), "fhi": 0, "gpos": self.gpos,
        }
        self.seq += 1
        if emit:
            self.out_lines.append(json.dumps(frame))
        return frame

    def truth(self) -> dict:
        """Hidden true plant state (available only in simulation; used to score estimators)."""
        o = cropm.outputs(self.xn, self.xs, self.crop)
        return {k: float(v) for k, v in o.items()}
