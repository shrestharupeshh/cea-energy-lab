// PlantPulse node - portable control core (no Arduino dependencies).
// Compiled into the ESP32 firmware and into the host-side unit tests (firmware/node/test_host).
#pragma once
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace pp {

constexpr float NANF = NAN;

// Hard limits compiled into the node. The host applies the same envelope before sending.
struct Limits {
  float air_t_min = 15.0f, air_t_max = 32.0f;     // setpoint range, C
  float air_t_trip = 36.0f;                       // over-temperature trip, C
  float rh_min = 40.0f, rh_max = 85.0f;           // setpoint range, %
  float led_max = 1.0f;                           // duty
  float fan_min = 0.15f;                          // minimum exhaust duty (CO2 / humidity floor)
  uint32_t comms_timeout_ms = 120000;             // host silence before "hold last recipe" mode
  uint32_t sensor_stale_ms = 15000;               // air sensor silence before heater lock-out
  uint32_t topup_max_ms = 60000;                  // longest single top-up
  uint32_t topup_budget_ms_per_h = 240000;        // flood guard
};

struct Setpoints {
  float air_t_day = 23.0f, air_t_night = 20.0f;
  float rh = 68.0f;
  float led_duty = 0.0f;                          // commanded duty during the photoperiod
  uint16_t lights_on_min = 360, lights_off_min = 1320;   // minutes of day (local)
  uint16_t ramp_min = 5;
  float mix_duty = 0.30f;
  bool pump_on = true;
};

enum class Mode : uint8_t { SAFE = 0, AUTO = 1, MANUAL = 2 };

struct Inputs {
  float air_t = NANF, rh = NANF;
  uint32_t air_age_ms = 0;                        // time since last valid air sample
  bool door_open = false, leak = false, float_low = false, float_high = false, estop_ok = true;
  uint32_t host_age_ms = 0;                       // time since last valid host frame
  uint16_t minute_of_day = 0;
};

struct Outputs {
  float heater = 0, fan = 0, mix = 0, led = 0;    // duties 0..1
  bool pump = false, humidifier = false, topup = false, gantry_enable = false;
  uint16_t faults = 0;
};

enum Fault : uint16_t {
  F_OVERTEMP = 1 << 0, F_SENSOR_STALE = 1 << 1, F_HOST_TIMEOUT = 1 << 2, F_LEAK = 1 << 3,
  F_DOOR = 1 << 4, F_ESTOP = 1 << 5, F_TOPUP_BUDGET = 1 << 6, F_FLOAT_HIGH = 1 << 7,
};

inline float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

class PI {
 public:
  PI(float kp, float ki, float lo, float hi) : kp_(kp), ki_(ki), lo_(lo), hi_(hi) {}
  float update(float err, float dt_s) {
    float u = kp_ * err + i_;
    float sat = clampf(u, lo_, hi_);
    // conditional integration (anti-windup): integrate only when not pushing further into saturation
    if ((u == sat) || (err > 0 && u < lo_) || (err < 0 && u > hi_)) i_ = clampf(i_ + ki_ * err * dt_s, lo_, hi_);
    return clampf(kp_ * err + i_, lo_, hi_);
  }
  void reset() { i_ = 0; }
  float integrator() const { return i_; }

 private:
  float kp_, ki_, lo_, hi_, i_ = 0;
};

// Photoperiod with linear ramps; handles schedules that wrap past midnight.
float light_fraction(uint16_t minute, uint16_t on_min, uint16_t off_min, uint16_t ramp_min);

class Controller {
 public:
  Limits lim;
  Setpoints sp;
  Mode mode = Mode::SAFE;
  Outputs manual;                                  // values used in MANUAL mode

  // dt_s: control period. Returns actuator commands with all interlocks applied.
  Outputs step(const Inputs& in, float dt_s);
  float active_air_setpoint(const Inputs& in) const;

 private:
  PI temp_pi_{0.35f, 0.01f, -1.0f, 1.0f};         // output +1 = full heat, -1 = full ventilation
  bool humid_on_ = false;
  uint32_t topup_run_ms_ = 0, topup_hour_ms_ = 0, hour_clock_ms_ = 0;
};

// ---- command protocol (host -> node), one ASCII line per command, see firmware/PROTOCOL.md
struct CommandResult {
  bool ok = false;
  long id = -1;
  char msg[48] = "";
  bool move = false; int station = -1;             // gantry request
  bool capture = false;                            // imaging sequence request
  bool time_set = false; uint32_t epoch = 0;
};

CommandResult handle_command(const char* line, Controller& c);
int format_ack(const CommandResult& r, char* buf, size_t n);

// Gantry kinematics
struct Gantry {
  float steps_per_mm = 80.0f;
  float stations_mm[4] = {40.0f, 200.0f, 400.0f, 600.0f};   // park, S1, S2, S3 (chamber x)
  float home_offset_mm = 20.0f;                             // chamber x of the home switch trip point
  long steps_for(int station) const {
    if (station < 0 || station > 3) return -1;
    return lroundf((stations_mm[station] - home_offset_mm) * steps_per_mm);
  }
};

}  // namespace pp
