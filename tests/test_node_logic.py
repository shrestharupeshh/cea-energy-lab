"""The Python port must behave like the C++ core (same cases as firmware/node/test_host/test_core.cpp)."""
import math
import shutil
import subprocess
from pathlib import Path

import pytest

from plantpulse.acquisition import node_logic as n
from plantpulse.acquisition.safety import Envelope, check_setpoints, to_node_command


def nominal(**kw):
    return n.Inputs(**{**dict(air_t=23.0, rh=68.0, air_age_ms=1000, host_age_ms=1000, minute_of_day=720), **kw})


def test_light_fraction():
    assert n.light_fraction(359, 360, 1320, 5) == 0 and n.light_fraction(720, 360, 1320, 5) == 1
    assert math.isclose(n.light_fraction(362, 360, 1320, 5), 0.4)
    assert n.light_fraction(10, 1200, 240, 0) == 1 and n.light_fraction(300, 1200, 240, 0) == 0


def test_commands_validated_atomically():
    c = n.Controller()
    assert n.handle_command("SET air_t_day=24 rh=70 led=0.74 on=360 off=1320 id=5", c)["ok"] and c.sp.air_t_day == 24
    assert not n.handle_command("SET air_t_day=40 rh=50", c)["ok"] and c.sp.rh == 70
    assert not n.handle_command("SET led=1.5", c)["ok"]
    assert not n.handle_command("SET on=0 off=1300", c)["ok"]
    assert not n.handle_command("SET air_t_day=nan", c)["ok"]
    assert not n.handle_command("FLASH everything", c)["ok"]
    assert n.handle_command("MOVE station=2", c)["station"] == 2 and not n.handle_command("MOVE station=9", c)["ok"]


def test_default_safe_and_auto_control():
    c = n.Controller()
    o = c.step(nominal(), 1.0)
    assert o.heater == 0 and o.led == 0 and o.pump
    n.handle_command("SET led=0.74", c)
    n.handle_command("MODE AUTO", c)
    for _ in range(60):
        o = c.step(nominal(air_t=20.0), 1.0)
    assert o.heater > 0.5 and math.isclose(o.led, 0.74)
    for _ in range(600):
        o = c.step(nominal(air_t=27.0), 1.0)
    assert o.heater == 0 and o.fan > 0.8


@pytest.mark.parametrize("kw,check", [
    (dict(air_t=37.0), lambda o: o.faults & n.F_OVERTEMP and o.heater == 0 and o.fan == 1 and o.led == 0),
    (dict(air_t=18.0, air_age_ms=60000), lambda o: o.faults & n.F_SENSOR_STALE and o.heater == 0),
    (dict(air_t=math.nan), lambda o: o.faults & n.F_SENSOR_STALE and o.heater == 0),
    (dict(leak=True), lambda o: not o.pump and not o.topup),
    (dict(door_open=True), lambda o: not o.gantry_enable),
    (dict(estop_ok=False), lambda o: o.heater == 0 and o.led == 0),
])
def test_interlocks(kw, check):
    c = n.Controller(mode=n.AUTO)
    c.sp.led_duty = 0.7
    assert check(c.step(nominal(**kw), 1.0))


def test_manual_mode_cannot_override_interlocks():
    c = n.Controller()
    n.handle_command("MAN heater=1 led=1 fan=0", c)
    n.handle_command("MODE MANUAL", c)
    assert c.step(nominal(), 1.0).heater == 1
    o = c.step(nominal(air_t=36.5), 1.0)
    assert o.heater == 0 and o.fan == 1


def test_topup_flood_guard():
    c = n.Controller(mode=n.AUTO)
    assert sum(c.step(nominal(float_low=True), 1.0).topup for _ in range(300)) == 60


def test_host_envelope():
    env = Envelope()
    ok, sp, _ = check_setpoints({"ppfd": 250, "photoperiod_h": 16, "air_t_day": 23, "air_t_night": 20, "rh": 68}, None, env, "recipe")
    assert ok and "led=0.7" in to_node_command(sp, 338.0)
    assert not check_setpoints({"ppfd": 320}, sp, env, "manual")[0]
    assert not check_setpoints({"ppfd": 300, "photoperiod_h": 18}, sp, env, "manual")[0]          # DLI 19.4
    assert not check_setpoints({"air_t_day": float("nan")}, sp, env, "manual")[0]
    assert not check_setpoints({"ppfd": 200}, sp, env, "twin")[0]                                  # not opted in
    ok, sp2, why = check_setpoints({"ppfd": 100}, sp, Envelope(allow_twin=True), "twin")
    assert ok and sp2["ppfd"] == 150 and why                                                       # rate limited


def test_firmware_core_host_tests():
    """Compile and run the C++ unit tests of the firmware control core, if a compiler is available."""
    if not shutil.which("g++"):
        pytest.skip("g++ not available")
    d = Path(__file__).resolve().parents[1] / "firmware" / "node" / "test_host"
    r = subprocess.run(["make", "-C", str(d), "test"], capture_output=True, text=True)
    assert r.returncode == 0 and "all tests passed" in r.stdout, r.stdout + r.stderr
