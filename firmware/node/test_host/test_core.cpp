// Host-side unit tests for the portable control core.  Build: make -C firmware/node/test_host
#include <cassert>
#include <cstdio>

#include "../lib/core/core.h"

using namespace pp;

static Inputs nominal() {
  Inputs in;
  in.air_t = 23.0f; in.rh = 68.0f; in.air_age_ms = 1000; in.host_age_ms = 1000; in.minute_of_day = 720;
  return in;
}

int main() {
  // photoperiod and ramps
  assert(light_fraction(359, 360, 1320, 5) == 0.0f);
  assert(light_fraction(720, 360, 1320, 5) == 1.0f);
  assert(std::fabs(light_fraction(362, 360, 1320, 5) - 0.4f) < 1e-6f);
  assert(light_fraction(1320, 360, 1320, 5) == 0.0f);
  assert(light_fraction(10, 1200, 240, 0) == 1.0f);          // wraps midnight
  assert(light_fraction(300, 1200, 240, 0) == 0.0f);

  Controller c;
  // default state is SAFE: no heat, no light
  Outputs o = c.step(nominal(), 1.0f);
  assert(o.heater == 0 && o.led == 0 && o.pump);

  // command parsing: valid set
  CommandResult r = handle_command("SET air_t_day=24 rh=70 led=0.74 on=360 off=1320 id=5", c);
  assert(r.ok && r.id == 5 && c.sp.air_t_day == 24.0f && std::fabs(c.sp.led_duty - 0.74f) < 1e-6f);
  // out-of-range is rejected atomically (nothing applied)
  r = handle_command("SET air_t_day=40 rh=50 id=6", c);
  assert(!r.ok && r.id == 6 && c.sp.air_t_day == 24.0f && c.sp.rh == 70.0f);   // rejection keeps its id
  r = handle_command("SET led=1.5", c);
  assert(!r.ok);
  r = handle_command("SET on=0 off=1300", c);                 // 21.7 h photoperiod
  assert(!r.ok && c.sp.lights_on_min == 360);
  r = handle_command("FLASH everything", c);
  assert(!r.ok);
  r = handle_command("SET air_t_day=nan", c);
  assert(!r.ok);
  r = handle_command("MODE AUTO id=7", c);
  assert(r.ok && c.mode == Mode::AUTO);
  r = handle_command("MOVE station=2 id=8", c);
  assert(r.ok && r.move && r.station == 2);
  r = handle_command("MOVE station=9", c);
  assert(!r.ok && !r.move);
  char buf[96];
  format_ack(r, buf, sizeof buf);
  assert(std::strstr(buf, "\"ok\":false"));

  // AUTO: lights on at noon, heating when cold, ventilation when warm
  Inputs in = nominal();
  in.air_t = 20.0f;
  for (int i = 0; i < 60; ++i) o = c.step(in, 1.0f);
  assert(o.heater > 0.5f && o.fan <= c.lim.fan_min + 1e-6f && std::fabs(o.led - 0.74f) < 1e-6f);
  in.air_t = 27.0f;
  for (int i = 0; i < 600; ++i) o = c.step(in, 1.0f);
  assert(o.heater == 0.0f && o.fan > 0.8f);
  // humidifier hysteresis
  in = nominal(); in.rh = 60.0f; o = c.step(in, 1.0f); assert(o.humidifier);
  in.rh = 69.0f; o = c.step(in, 1.0f); assert(o.humidifier);
  in.rh = 71.0f; o = c.step(in, 1.0f); assert(!o.humidifier);

  // interlocks
  in = nominal(); in.air_t = 37.0f; o = c.step(in, 1.0f);
  assert((o.faults & F_OVERTEMP) && o.heater == 0 && o.fan == 1.0f && o.led == 0);
  in = nominal(); in.air_t = 18.0f; in.air_age_ms = 60000; o = c.step(in, 1.0f);
  assert((o.faults & F_SENSOR_STALE) && o.heater == 0);
  in = nominal(); in.air_t = NANF; o = c.step(in, 1.0f);
  assert((o.faults & F_SENSOR_STALE) && o.heater == 0);
  in = nominal(); in.leak = true; o = c.step(in, 1.0f);
  assert((o.faults & F_LEAK) && !o.pump && !o.topup);
  in = nominal(); in.door_open = true; o = c.step(in, 1.0f);
  assert(!o.gantry_enable);
  in = nominal(); in.estop_ok = false; o = c.step(in, 1.0f);
  assert(o.heater == 0 && o.led == 0);
  // host silence: recipe continues (lights stay on) but heater is capped
  in = nominal(); in.air_t = 15.0f; in.host_age_ms = 200000;
  for (int i = 0; i < 120; ++i) o = c.step(in, 1.0f);
  assert((o.faults & F_HOST_TIMEOUT) && o.heater <= 0.5f && o.led > 0.7f);

  // top-up flood guard: stops after 60 s continuous even if the float stays low
  Controller c2; c2.mode = Mode::AUTO;
  in = nominal(); in.float_low = true;
  int on_s = 0;
  for (int i = 0; i < 300; ++i) on_s += c2.step(in, 1.0f).topup ? 1 : 0;
  assert(on_s == 60);
  in.float_high = true;
  assert(!c2.step(in, 1.0f).topup);

  // MANUAL mode still obeys interlocks
  Controller c3;
  handle_command("MAN heater=1 led=1 fan=0", c3);
  handle_command("MODE MANUAL", c3);
  in = nominal(); o = c3.step(in, 1.0f); assert(o.heater == 1.0f && o.led == 1.0f);
  in.air_t = 36.5f; o = c3.step(in, 1.0f); assert(o.heater == 0 && o.fan == 1.0f);

  // gantry kinematics
  Gantry g;
  assert(g.steps_for(0) == 1600 && g.steps_for(3) == 46400 && g.steps_for(4) == -1);

  std::puts("firmware core: all tests passed");
  return 0;
}
