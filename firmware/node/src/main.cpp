// PlantPulse node firmware (ESP32-S3-DevKitC-1 on carrier PP-E-001).
// Hardware layer only: all decisions are made in lib/core (unit-tested on the host).
// STATUS: written against the carrier netlist; NOT yet compiled for the target or run on hardware.
#include <AccelStepper.h>
#include <Adafruit_AS7341.h>
#include <Adafruit_INA228.h>
#include <Adafruit_MCP23X17.h>
#include <Adafruit_NAU7802.h>
#include <Adafruit_SHT4x.h>
#include <Arduino.h>
#include <DallasTemperature.h>
#include <OneWire.h>
#include <SparkFun_SCD30_Arduino_Library.h>
#include <Wire.h>
#include <esp_task_wdt.h>

#include "core.h"

#ifndef PP_POD_ID
#define PP_POD_ID 1
#endif

// ---- pin map (see hardware/electrical/pcb/node_netlist.py)
namespace pin {
const int SDA = 8, SCL = 9, OW = 4, LED_PWM = 5, IMG_LED = 6, CAM_TRIG = 7, CAM_BUSY = 15;
const int HEATER = 16, PUMP = 17, PERI = 18, HUMID = 21;
const int FAN_PWM[3] = {10, 11, 12};        // exhaust, mixing, LED bay (inverted by 2N7000)
const int TACH[2] = {13, 14};
const int FLOW = 1, EXP_INT = 2, STEP_EN_N = 42, DIR = 41, STEP = 40, OUT_EN_N = 39, ENDSTOP = 47;
}  // namespace pin
namespace xp { const int FLOAT_LO = 0, FLOAT_HI = 1, LEAK = 2, DOOR = 3, ESTOP_OK = 4; }  // MCP23017 port A

// LEDC channels
enum { CH_LED = 0, CH_HEAT = 1, CH_FAN0 = 2, CH_FAN1 = 3, CH_FAN2 = 4 };

pp::Controller ctl;
pp::Gantry gantry;
Adafruit_SHT4x sht;
SCD30 scd;
Adafruit_AS7341 as7341;
Adafruit_NAU7802 nau;
Adafruit_INA228 ina_led, ina_act;
Adafruit_MCP23X17 mcp;
OneWire ow(pin::OW);
DallasTemperature ds(&ow);
AccelStepper stepper(AccelStepper::DRIVER, pin::STEP, pin::DIR);

struct Present { bool sht, scd, as7341, nau, ina_led, ina_act, mcp; } present;
volatile uint32_t flow_pulses = 0, tach_pulses[2] = {0, 0};
void IRAM_ATTR isr_flow() { flow_pulses++; }
void IRAM_ATTR isr_tach0() { tach_pulses[0]++; }
void IRAM_ATTR isr_tach1() { tach_pulses[1]++; }

uint32_t last_host_ms = 0, last_air_ms = 0, epoch_at_sync = 0, ms_at_sync = 0, seq = 0;
float air_t = NAN, rh = NAN, co2 = NAN, sol_t[2] = {NAN, NAN}, ph = NAN, ec = NAN, res_g = NAN;
float par_raw = NAN, led_w = NAN, act_w = NAN, led_wh = 0, act_wh = 0;
bool homed = false;
enum class ImgState { IDLE, LEDS_OFF, WAIT_CAM } img_state = ImgState::IDLE;
uint32_t img_t0 = 0;
bool img_blank = false;                       // grow LEDs blanked during an exposure

// Atlas EZO (I2C mode): send "R", wait 900 ms, read ASCII reply. Non-blocking state machine.
struct Ezo {
  uint8_t addr; uint32_t t_req = 0; bool pending = false; float value = NAN;
  void poll() {
    if (!pending) {
      Wire.beginTransmission(addr); Wire.write('R');
      if (Wire.endTransmission() == 0) { pending = true; t_req = millis(); }
    } else if (millis() - t_req > 900) {
      Wire.requestFrom((int)addr, 20);
      if (Wire.available() && Wire.read() == 1) {
        char b[20]; int n = 0;
        while (Wire.available() && n < 19) { char ch = Wire.read(); if (ch) b[n++] = ch; }
        b[n] = 0; value = atof(b);
      }
      pending = false;
    }
  }
} ezo_ph{0x63}, ezo_ec{0x64};

void set_duty(int ch, float d, bool inverted = false) {
  d = pp::clampf(d, 0, 1);
  ledcWrite(ch, (uint32_t)lroundf((inverted ? 1.0f - d : d) * 1023));
}

uint16_t minute_of_day() {
  if (!epoch_at_sync) return 0;               // until the host sets the time, lights stay off (on==off never true)
  uint32_t now = epoch_at_sync + (millis() - ms_at_sync) / 1000;
  return (now % 86400UL) / 60;                // host sends local-time epoch
}

void apply(const pp::Outputs& o) {
  set_duty(CH_LED, img_blank ? 0.0f : o.led);
  set_duty(CH_HEAT, o.heater);
  set_duty(CH_FAN0, o.fan, true);
  set_duty(CH_FAN1, o.mix, true);
  set_duty(CH_FAN2, o.led > 0.02f ? 0.3f + 0.7f * o.led : 0.0f, true);   // LED bay fan follows LED power
  digitalWrite(pin::PUMP, o.pump);
  digitalWrite(pin::PERI, o.topup);
  digitalWrite(pin::HUMID, o.humidifier);
  if (!o.gantry_enable) { stepper.stop(); }
}

void home_gantry() {
  digitalWrite(pin::STEP_EN_N, LOW);
  stepper.setMaxSpeed(1600); stepper.setAcceleration(4000);
  stepper.move(-60000);
  uint32_t t0 = millis();
  while (digitalRead(pin::ENDSTOP) == HIGH && millis() - t0 < 30000) { stepper.run(); esp_task_wdt_reset(); }
  stepper.setCurrentPosition(0);
  stepper.runToNewPosition(160);              // back off 2 mm, re-approach slowly for repeatability
  stepper.setMaxSpeed(160);
  stepper.move(-400);
  while (digitalRead(pin::ENDSTOP) == HIGH && stepper.distanceToGo() != 0) stepper.run();
  homed = digitalRead(pin::ENDSTOP) == LOW;
  stepper.setCurrentPosition(0);
  stepper.setMaxSpeed(4000);
  digitalWrite(pin::STEP_EN_N, HIGH);
}

void handle_line(const char* line) {
  pp::CommandResult r = pp::handle_command(line, ctl);
  if (r.ok) last_host_ms = millis();
  if (r.time_set) { epoch_at_sync = r.epoch; ms_at_sync = millis(); }
  if (r.move) {
    if (!homed) home_gantry();
    digitalWrite(pin::STEP_EN_N, LOW);
    stepper.moveTo(gantry.steps_for(r.station));
  }
  if (r.capture && img_state == ImgState::IDLE) { img_state = ImgState::LEDS_OFF; img_t0 = millis(); }
  char buf[128];
  pp::format_ack(r, buf, sizeof buf);
  Serial.println(buf);
}

void imaging_task() {
  switch (img_state) {
    case ImgState::IDLE: break;
    case ImgState::LEDS_OFF:                  // grow LEDs off, imaging ring on, settle 500 ms
      img_blank = true; set_duty(CH_LED, 0); digitalWrite(pin::IMG_LED, HIGH);
      if (millis() - img_t0 > 500) { digitalWrite(pin::CAM_TRIG, HIGH); img_state = ImgState::WAIT_CAM; img_t0 = millis(); }
      break;
    case ImgState::WAIT_CAM:                  // camera node raises BUSY while exposing; 4 s timeout
      if ((millis() - img_t0 > 300 && digitalRead(pin::CAM_BUSY) == LOW) || millis() - img_t0 > 4000) {
        digitalWrite(pin::CAM_TRIG, LOW); digitalWrite(pin::IMG_LED, LOW); img_blank = false;
        Serial.printf("{\"t\":\"E\",\"ev\":\"capture_done\",\"ms\":%lu,\"pos\":%ld}\n", millis(), stepper.currentPosition());
        img_state = ImgState::IDLE;
      }
      break;
  }
}

void setup() {
  // Outputs stay disabled (buffer hi-Z, gates pulled down) until setup has finished.
  pinMode(pin::OUT_EN_N, OUTPUT); digitalWrite(pin::OUT_EN_N, HIGH);
  for (int p : {pin::PUMP, pin::PERI, pin::HUMID, pin::IMG_LED, pin::CAM_TRIG, pin::STEP_EN_N}) { pinMode(p, OUTPUT); digitalWrite(p, LOW); }
  digitalWrite(pin::STEP_EN_N, HIGH);
  pinMode(pin::CAM_BUSY, INPUT_PULLDOWN); pinMode(pin::ENDSTOP, INPUT_PULLUP); pinMode(pin::FLOW, INPUT);
  for (int t : pin::TACH) pinMode(t, INPUT_PULLUP);
  ledcSetup(CH_LED, 1000, 10); ledcAttachPin(pin::LED_PWM, CH_LED);
  ledcSetup(CH_HEAT, 10, 10); ledcAttachPin(pin::HEATER, CH_HEAT);
  for (int i = 0; i < 3; ++i) { ledcSetup(CH_FAN0 + i, 25000, 10); ledcAttachPin(pin::FAN_PWM[i], CH_FAN0 + i); set_duty(CH_FAN0 + i, 0, true); }
  Serial.begin(115200);
  Wire.begin(pin::SDA, pin::SCL, 100000);
  present.sht = sht.begin(); if (present.sht) { sht.setPrecision(SHT4X_HIGH_PRECISION); sht.setHeater(SHT4X_NO_HEATER); }
  present.scd = scd.begin(); if (present.scd) { scd.setMeasurementInterval(5); scd.setAutoSelfCalibration(false); }
  present.as7341 = as7341.begin();
  present.nau = nau.begin();
  present.ina_led = ina_led.begin(0x40); present.ina_act = ina_act.begin(0x41);
  if (present.ina_led) ina_led.setShunt(0.015, 10.0);
  if (present.ina_act) ina_act.setShunt(0.015, 10.0);
  present.mcp = mcp.begin_I2C(0x20);
  if (present.mcp) for (int i = 0; i < 8; ++i) mcp.pinMode(i, INPUT);
  ds.begin(); ds.setWaitForConversion(false); ds.setResolution(12);
  attachInterrupt(pin::FLOW, isr_flow, RISING);
  attachInterrupt(pin::TACH[0], isr_tach0, FALLING);
  attachInterrupt(pin::TACH[1], isr_tach1, FALLING);
  esp_task_wdt_init(8, true); esp_task_wdt_add(NULL);
  Serial.printf("{\"t\":\"H\",\"pod\":%d,\"fw\":\"0.1.0\",\"sht\":%d,\"scd\":%d,\"as\":%d,\"nau\":%d,\"ina\":%d,\"mcp\":%d}\n",
                PP_POD_ID, present.sht, present.scd, present.as7341, present.nau, present.ina_led + present.ina_act, present.mcp);
  digitalWrite(pin::OUT_EN_N, LOW);           // enable the output buffer only now
}

void loop() {
  static char line[160]; static size_t n = 0; static uint32_t t_ctl = 0;
  esp_task_wdt_reset();
  stepper.run();
  if (stepper.distanceToGo() == 0 && img_state == ImgState::IDLE) digitalWrite(pin::STEP_EN_N, HIGH);
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n') { line[n] = 0; if (n) handle_line(line); n = 0; }
    else if (n < sizeof(line) - 1) line[n++] = ch;
  }
  imaging_task();
  if (millis() - t_ctl < 1000) return;
  float dt = (millis() - t_ctl) / 1000.0f; t_ctl = millis();

  // ---- acquisition (1 Hz)
  if (present.sht) { sensors_event_t h, t; if (sht.getEvent(&h, &t)) { air_t = t.temperature; rh = h.relative_humidity; last_air_ms = millis(); } }
  if (present.scd && scd.dataAvailable()) co2 = scd.getCO2();
  if (present.as7341 && as7341.readAllChannels()) {
    par_raw = 0; for (as7341_color_channel_t c2 : {AS7341_CHANNEL_415nm_F1, AS7341_CHANNEL_445nm_F2, AS7341_CHANNEL_480nm_F3, AS7341_CHANNEL_515nm_F4,
                                                    AS7341_CHANNEL_555nm_F5, AS7341_CHANNEL_590nm_F6, AS7341_CHANNEL_630nm_F7, AS7341_CHANNEL_680nm_F8})
      par_raw += as7341.getChannel(c2);
  }
  static bool ds_req = false;
  if (ds_req) { sol_t[0] = ds.getTempCByIndex(0); sol_t[1] = ds.getTempCByIndex(1); }
  ds.requestTemperatures(); ds_req = true;
  ezo_ph.poll(); ezo_ec.poll(); ph = ezo_ph.value; ec = ezo_ec.value;
  if (present.nau && nau.available()) res_g = nau.read();            // raw counts; calibration applied on the host
  if (present.ina_led) { led_w = ina_led.readPower() / 1000.0f; led_wh += led_w * dt / 3600.0f; }
  if (present.ina_act) { act_w = ina_act.readPower() / 1000.0f; act_wh += act_w * dt / 3600.0f; }
  noInterrupts(); uint32_t fp = flow_pulses; flow_pulses = 0; uint32_t tp0 = tach_pulses[0]; tach_pulses[0] = 0; uint32_t tp1 = tach_pulses[1]; tach_pulses[1] = 0; interrupts();

  // ---- control
  pp::Inputs in;
  in.air_t = air_t; in.rh = rh; in.air_age_ms = millis() - last_air_ms; in.host_age_ms = millis() - last_host_ms;
  in.minute_of_day = minute_of_day();
  if (present.mcp) {
    uint8_t a = mcp.readGPIOA();
    in.float_low = !(a & (1 << xp::FLOAT_LO)); in.float_high = !(a & (1 << xp::FLOAT_HI));
    in.leak = !(a & (1 << xp::LEAK)); in.door_open = (a & (1 << xp::DOOR)); in.estop_ok = (a & (1 << xp::ESTOP_OK));
  }
  if (!epoch_at_sync) ctl.sp.lights_on_min = ctl.sp.lights_off_min;   // no time base yet: lights off
  pp::Outputs o = ctl.step(in, dt);
  apply(o);

  // ---- telemetry frame (JSON line)
  Serial.printf("{\"t\":\"S\",\"pod\":%d,\"seq\":%lu,\"ms\":%lu,\"mode\":%d,\"faults\":%u,"
                "\"air_t\":%.3f,\"rh\":%.2f,\"co2\":%.0f,\"par_raw\":%.0f,\"sol_t\":%.3f,\"sol_t2\":%.3f,\"ph\":%.3f,\"ec\":%.1f,"
                "\"res_raw\":%.0f,\"flow_hz\":%.1f,\"tach0_hz\":%.1f,\"tach1_hz\":%.1f,\"led_w\":%.3f,\"act_w\":%.3f,\"led_wh\":%.4f,\"act_wh\":%.4f,"
                "\"u_heat\":%.3f,\"u_fan\":%.3f,\"u_mix\":%.3f,\"u_led\":%.3f,\"pump\":%d,\"humid\":%d,\"topup\":%d,"
                "\"door\":%d,\"leak\":%d,\"flo\":%d,\"fhi\":%d,\"gpos\":%ld}\n",
                PP_POD_ID, (unsigned long)seq++, millis(), (int)ctl.mode, o.faults, air_t, rh, co2, par_raw, sol_t[0], sol_t[1], ph, ec,
                res_g, fp / dt, tp0 / dt, tp1 / dt, led_w, act_w, led_wh, act_wh, o.heater, o.fan, o.mix, o.led, o.pump, o.humidifier, o.topup,
                in.door_open, in.leak, in.float_low, in.float_high, stepper.currentPosition());
}
