"""Electrical load schedule, rail sizing, fusing and wire voltage drop."""
from __future__ import annotations

from dataclasses import dataclass, field

RHO_CU = 1.72e-8  # ohm.m
AWG_MM2 = {24: 0.205, 22: 0.326, 20: 0.518, 18: 0.823, 16: 1.31, 14: 2.08}


def voltage_drop(current_a: float, length_m: float, awg: int) -> float:
    """Round-trip voltage drop (V) in a two-conductor copper run."""
    return 2 * current_a * RHO_CU * length_m / (AWG_MM2[awg] * 1e-6)


@dataclass
class Load:
    name: str
    rail: str           # "48V_LED", "24V_ACT", "24V_LOGIC", "MAINS"
    peak_w: float
    duty_typ: float     # time-averaged fraction over 24 h in the control recipe
    note: str = ""

    @property
    def avg_w(self) -> float:
        return self.peak_w * self.duty_typ


@dataclass
class ElectricalResult:
    loads: list[Load]
    rail_peak_w: dict = field(default_factory=dict)
    rail_avg_w: dict = field(default_factory=dict)
    pod_peak_w: float = 0.0
    pod_avg_w: float = 0.0
    facility_peak_wall_w: float = 0.0
    facility_avg_wall_w: float = 0.0
    kwh_per_cycle_facility: float = 0.0
    psu24_load_frac: float = 0.0
    psu48_load_frac: float = 0.0
    fuses: dict = field(default_factory=dict)
    drops: dict = field(default_factory=dict)
    mains_current_a: float = 0.0

    def as_rows(self):
        rows = [(f"Rail {r} per pod", f"peak {self.rail_peak_w[r]:.1f} W / mean {self.rail_avg_w[r]:.1f} W", "") for r in self.rail_peak_w]
        rows += [
            ("Pod total (DC side)", f"peak {self.pod_peak_w:.0f} W / mean {self.pod_avg_w:.0f} W", "control recipe, 20 C room"),
            ("Facility at the wall (4 pods + central + air pump)", f"peak {self.facility_peak_wall_w:.0f} W / mean {self.facility_avg_wall_w:.0f} W", "PSU efficiency 0.90"),
            ("Facility energy per 28-day cycle", f"{self.kwh_per_cycle_facility:.0f} kWh", "estimate; metered in operation"),
            ("24 V supply loading", f"{100 * self.psu24_load_frac:.0f} %", "all heaters on simultaneously"),
            ("48 V supply loading", f"{100 * self.psu48_load_frac:.0f} %", ""),
            ("Mains current at peak (120 V)", f"{self.mains_current_a:.1f} A", "15 A GFCI circuit adequate"),
        ]
        rows += [(f"Fuse {k}", v, "") for k, v in self.fuses.items()]
        rows += [(f"Voltage drop {k}", f"{v[0]:.2f} V ({v[1]:.1f} %)", "") for k, v in self.drops.items()]
        return rows


def analyse(d: dict, led_w_full: float, led_w_nominal: float, heater_duty_typ: float = 0.25) -> ElectricalResult:
    el, air, hy, lt = d["electrical"], d["air"], d["hydraulics"], d["lighting"]
    photo = lt["nominal_photoperiod_h"] / 24
    loads = [
        Load("LED strips via 3 x CC driver", "48V_LED", led_w_full, photo * led_w_nominal / led_w_full, "dimmed to nominal PPFD"),
        Load("PTC heater", "24V_ACT", air["heater_power_w"], heater_duty_typ, "duty depends on setpoint and room"),
        Load("Exhaust + mixing + LED-bay fans", "24V_ACT", 3 * air["fan_power_w"], 0.8),
        Load("Circulation pump", "24V_ACT", hy["pump_power_w"], 1.0),
        Load("Peristaltic top-up pump", "24V_ACT", el["peristaltic_w"], 0.01),
        Load("Humidifier", "24V_ACT", 2.5, 0.2),
        Load("Gantry stepper", "24V_ACT", el["stepper_w"], 0.02, "driver disabled between moves"),
        Load("Imaging LED ring", "24V_ACT", el["imaging_led_w"], 0.005),
        Load("Node MCU + sensors", "24V_LOGIC", el["node_logic_w"], 1.0),
        Load("Camera node (Pi Zero 2 W + HQ cam)", "24V_LOGIC", el["camera_node_w"], 1.0),
    ]
    res = ElectricalResult(loads=loads)
    for r in ("48V_LED", "24V_ACT", "24V_LOGIC"):
        res.rail_peak_w[r] = sum(l.peak_w for l in loads if l.rail == r)
        res.rail_avg_w[r] = sum(l.avg_w for l in loads if l.rail == r)
    res.pod_peak_w = sum(res.rail_peak_w.values())
    res.pod_avg_w = sum(res.rail_avg_w.values())
    n = d["facility"]["n_pods"]
    eff = el["psu_efficiency"]
    res.facility_peak_wall_w = n * res.pod_peak_w / eff + el["central_w"] + el["air_pump_w"]
    res.facility_avg_wall_w = n * res.pod_avg_w / eff + el["central_w"] + el["air_pump_w"]
    res.kwh_per_cycle_facility = res.facility_avg_wall_w * 24 * 28 / 1000
    res.psu24_load_frac = n * (res.rail_peak_w["24V_ACT"] + res.rail_peak_w["24V_LOGIC"]) / el["psu_24_w"]
    res.psu48_load_frac = n * res.rail_peak_w["48V_LED"] / el["psu_48_w"]
    res.mains_current_a = res.facility_peak_wall_w / el["mains_v"]
    i_led = res.rail_peak_w["48V_LED"] / 48
    i_act = res.rail_peak_w["24V_ACT"] / 24
    i_log = res.rail_peak_w["24V_LOGIC"] / 24
    res.fuses = {
        "48V_LED feed per pod": f"{i_led:.2f} A load -> 2 A fast blade fuse",
        "24V_ACT feed per pod": f"{i_act:.2f} A load -> 7.5 A blade fuse",
        "24V_LOGIC feed per pod": f"{i_log:.2f} A load -> 1 A blade fuse",
        "Mains inlet": f"{res.mains_current_a:.1f} A load -> 10 A slow-blow in IEC inlet",
    }
    for name, i, v, awg in (("48V_LED 3 m AWG18", i_led, 48, 18), ("24V_ACT 3 m AWG16", i_act, 24, 16), ("24V_LOGIC 3 m AWG20", i_log, 24, 20)):
        vd = voltage_drop(i, 3.0, awg)
        res.drops[name] = (vd, 100 * vd / v)
    return res
