#include "core.h"

#include <cstdlib>

namespace pp {

float light_fraction(uint16_t minute, uint16_t on_min, uint16_t off_min, uint16_t ramp_min) {
  if (on_min == off_min) return 0.0f;
  // minutes since lights-on, modulo one day
  int since_on = ((int)minute - (int)on_min + 1440) % 1440;
  int length = ((int)off_min - (int)on_min + 1440) % 1440;
  if (since_on >= length) return 0.0f;
  if (ramp_min == 0) return 1.0f;
  float up = (float)since_on / ramp_min;
  float down = (float)(length - since_on) / ramp_min;
  float f = up < down ? up : down;
  return clampf(f, 0.0f, 1.0f);
}

float Controller::active_air_setpoint(const Inputs& in) const {
  bool day = light_fraction(in.minute_of_day, sp.lights_on_min, sp.lights_off_min, 0) > 0.0f;
  return clampf(day ? sp.air_t_day : sp.air_t_night, lim.air_t_min, lim.air_t_max);
}

Outputs Controller::step(const Inputs& in, float dt_s) {
  Outputs o;
  uint32_t dt_ms = (uint32_t)(dt_s * 1000.0f);

  // ---- fault evaluation (independent of mode)
  bool air_valid = !std::isnan(in.air_t) && !std::isnan(in.rh) && in.air_age_ms < lim.sensor_stale_ms;
  if (!air_valid) o.faults |= F_SENSOR_STALE;
  if (air_valid && in.air_t >= lim.air_t_trip) o.faults |= F_OVERTEMP;
  if (in.host_age_ms > lim.comms_timeout_ms) o.faults |= F_HOST_TIMEOUT;
  if (in.leak) o.faults |= F_LEAK;
  if (in.door_open) o.faults |= F_DOOR;
  if (!in.estop_ok) o.faults |= F_ESTOP;
  if (in.float_high) o.faults |= F_FLOAT_HIGH;

  // ---- nominal commands
  if (mode == Mode::MANUAL) {
    o = manual;
    o.faults = 0;
    // re-evaluate faults onto the manual command set
    if (!air_valid) o.faults |= F_SENSOR_STALE;
    if (air_valid && in.air_t >= lim.air_t_trip) o.faults |= F_OVERTEMP;
    if (in.host_age_ms > lim.comms_timeout_ms) o.faults |= F_HOST_TIMEOUT;
    if (in.leak) o.faults |= F_LEAK;
    if (in.door_open) o.faults |= F_DOOR;
    if (!in.estop_ok) o.faults |= F_ESTOP;
    if (in.float_high) o.faults |= F_FLOAT_HIGH;
    o.led = clampf(o.led, 0.0f, lim.led_max);
    o.heater = clampf(o.heater, 0.0f, 1.0f);
    o.fan = clampf(o.fan, 0.0f, 1.0f);
    o.mix = clampf(o.mix, 0.0f, 1.0f);
  } else if (mode == Mode::AUTO) {
    float lf = light_fraction(in.minute_of_day, sp.lights_on_min, sp.lights_off_min, sp.ramp_min);
    o.led = clampf(sp.led_duty, 0.0f, lim.led_max) * lf;
    o.mix = clampf(sp.mix_duty, 0.0f, 1.0f);
    o.pump = sp.pump_on;
    o.fan = lim.fan_min;
    if (air_valid) {
      float u = temp_pi_.update(active_air_setpoint(in) - in.air_t, dt_s);
      if (u > 0) o.heater = u;
      else o.fan = lim.fan_min + (-u) * (1.0f - lim.fan_min);
      float rh_sp = clampf(sp.rh, lim.rh_min, lim.rh_max);
      if (in.rh < rh_sp - 2.0f) humid_on_ = true;
      if (in.rh > rh_sp) humid_on_ = false;
      o.humidifier = humid_on_;
      if (in.rh > rh_sp + 5.0f) {                  // dehumidify by ventilation
        float extra = clampf((in.rh - rh_sp - 5.0f) / 10.0f, 0.0f, 1.0f);
        float fan_h = lim.fan_min + extra * (1.0f - lim.fan_min);
        if (fan_h > o.fan) o.fan = fan_h;
      }
    } else {
      temp_pi_.reset();
      humid_on_ = false;
    }
    // level control with flood guard
    hour_clock_ms_ += dt_ms;
    if (hour_clock_ms_ >= 3600000UL) { hour_clock_ms_ = 0; topup_hour_ms_ = 0; }
    bool want = in.float_low && !in.float_high;
    if (want && topup_run_ms_ < lim.topup_max_ms && topup_hour_ms_ < lim.topup_budget_ms_per_h) {
      o.topup = true;
      topup_run_ms_ += dt_ms;
      topup_hour_ms_ += dt_ms;
    } else if (!want) {
      topup_run_ms_ = 0;
    }
    if (topup_hour_ms_ >= lim.topup_budget_ms_per_h) o.faults |= F_TOPUP_BUDGET;
    o.gantry_enable = true;
  } else {  // SAFE: circulation and air mixing only
    o.pump = true;
    o.mix = 0.3f;
    o.fan = lim.fan_min;
    temp_pi_.reset();
  }

  // ---- interlocks (always last, cannot be overridden by mode)
  if (o.faults & (F_OVERTEMP | F_SENSOR_STALE)) o.heater = 0.0f;
  if (o.faults & F_OVERTEMP) { o.fan = 1.0f; o.led = 0.0f; }
  if (o.faults & F_HOST_TIMEOUT) {                 // hold last recipe, but never heat hard without supervision
    if (o.heater > 0.5f) o.heater = 0.5f;
  }
  if (o.faults & (F_LEAK | F_FLOAT_HIGH)) { o.pump = false; o.topup = false; }
  if (o.faults & F_DOOR) o.gantry_enable = false;
  if (o.faults & F_ESTOP) { o.heater = 0; o.led = 0; o.humidifier = false; o.topup = false; o.gantry_enable = false; }
  return o;
}

// ------------------------------------------------------------------ command parsing
static bool parse_kv(const char* tok, char* key, size_t kn, float* val) {
  const char* eq = strchr(tok, '=');
  if (!eq || eq == tok) return false;
  size_t len = (size_t)(eq - tok);
  if (len >= kn) return false;
  memcpy(key, tok, len);
  key[len] = 0;
  char* end = nullptr;
  *val = strtof(eq + 1, &end);
  return end != eq + 1 && (*end == 0);
}

CommandResult handle_command(const char* line, Controller& c) {
  CommandResult r;
  char buf[160];
  strncpy(buf, line, sizeof(buf) - 1);
  buf[sizeof(buf) - 1] = 0;
  // Extract the id first so that a rejected command is still acknowledged with its id.
  if (const char* idp = strstr(line, " id=")) {
    char* end = nullptr;
    long v = strtol(idp + 4, &end, 10);
    if (end != idp + 4) r.id = v;
  }
  char* save = nullptr;
  char* verb = strtok_r(buf, " \r\n", &save);
  if (!verb) { snprintf(r.msg, sizeof(r.msg), "empty"); return r; }
  Setpoints sp = c.sp;          // staged: applied only if every token is valid
  Outputs man = c.manual;
  Mode mode = c.mode;
  bool is_set = !strcmp(verb, "SET"), is_man = !strcmp(verb, "MAN"), is_mode = !strcmp(verb, "MODE");
  bool is_move = !strcmp(verb, "MOVE"), is_cap = !strcmp(verb, "CAPTURE"), is_time = !strcmp(verb, "TIME");
  bool is_ping = !strcmp(verb, "PING");
  if (!(is_set || is_man || is_mode || is_move || is_cap || is_time || is_ping)) {
    snprintf(r.msg, sizeof(r.msg), "unknown verb");
    return r;
  }
  bool bad = false;
  for (char* tok = strtok_r(nullptr, " \r\n", &save); tok; tok = strtok_r(nullptr, " \r\n", &save)) {
    char key[20];
    float v;
    if (is_mode && strchr(tok, '=') == nullptr) {
      if (!strcmp(tok, "AUTO")) mode = Mode::AUTO;
      else if (!strcmp(tok, "MANUAL")) mode = Mode::MANUAL;
      else if (!strcmp(tok, "SAFE")) mode = Mode::SAFE;
      else bad = true;
      continue;
    }
    if (!parse_kv(tok, key, sizeof(key), &v) || std::isnan(v)) { bad = true; break; }
    if (!strcmp(key, "id")) { r.id = (long)v; continue; }
    if (is_set) {
      const Limits& L = c.lim;
      if (!strcmp(key, "air_t_day")) { if (v < L.air_t_min || v > L.air_t_max) bad = true; else sp.air_t_day = v; }
      else if (!strcmp(key, "air_t_night")) { if (v < L.air_t_min || v > L.air_t_max) bad = true; else sp.air_t_night = v; }
      else if (!strcmp(key, "rh")) { if (v < L.rh_min || v > L.rh_max) bad = true; else sp.rh = v; }
      else if (!strcmp(key, "led")) { if (v < 0 || v > L.led_max) bad = true; else sp.led_duty = v; }
      else if (!strcmp(key, "on")) { if (v < 0 || v >= 1440) bad = true; else sp.lights_on_min = (uint16_t)v; }
      else if (!strcmp(key, "off")) { if (v < 0 || v >= 1440) bad = true; else sp.lights_off_min = (uint16_t)v; }
      else if (!strcmp(key, "ramp")) { if (v < 0 || v > 60) bad = true; else sp.ramp_min = (uint16_t)v; }
      else if (!strcmp(key, "mix")) { if (v < 0 || v > 1) bad = true; else sp.mix_duty = v; }
      else if (!strcmp(key, "pump")) sp.pump_on = v > 0.5f;
      else bad = true;
    } else if (is_man) {
      if (v < 0 || v > 1) { bad = true; break; }
      if (!strcmp(key, "heater")) man.heater = v;
      else if (!strcmp(key, "fan")) man.fan = v;
      else if (!strcmp(key, "mix")) man.mix = v;
      else if (!strcmp(key, "led")) man.led = v;
      else if (!strcmp(key, "pump")) man.pump = v > 0.5f;
      else if (!strcmp(key, "humid")) man.humidifier = v > 0.5f;
      else if (!strcmp(key, "topup")) man.topup = v > 0.5f;
      else bad = true;
    } else if (is_move) {
      if (!strcmp(key, "station") && v >= 0 && v <= 3) { r.move = true; r.station = (int)v; } else bad = true;
    } else if (is_time) {
      if (!strcmp(key, "epoch") && v > 1.6e9f) { r.time_set = true; r.epoch = (uint32_t)strtoul(strchr(tok, '=') + 1, nullptr, 10); }
      else bad = true;
    } else if (is_cap || is_ping) {
      bad = true;   // no arguments other than id
    }
    if (bad) break;
  }
  if (bad) { snprintf(r.msg, sizeof(r.msg), "rejected"); r.move = false; r.time_set = false; return r; }
  // photoperiod sanity: at least 4 h of darkness
  if (is_set) {
    int length = ((int)sp.lights_off_min - (int)sp.lights_on_min + 1440) % 1440;
    if (length > 1200) { snprintf(r.msg, sizeof(r.msg), "photoperiod>20h"); return r; }
    c.sp = sp;
  }
  if (is_man) c.manual = man;
  if (is_mode) c.mode = mode;
  if (is_cap) r.capture = true;
  r.ok = true;
  snprintf(r.msg, sizeof(r.msg), "ok");
  return r;
}

int format_ack(const CommandResult& r, char* buf, size_t n) {
  return snprintf(buf, n, "{\"t\":\"A\",\"id\":%ld,\"ok\":%s,\"msg\":\"%s\"}", r.id, r.ok ? "true" : "false", r.msg);
}

}  // namespace pp
