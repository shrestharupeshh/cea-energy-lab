# Environmental control system

## Controlled and monitored variables

| Variable | Sensor | Actuator | Control law (on the node) | Achievable range (design calc) |
|----------|--------|----------|---------------------------|--------------------------------|
| Air temperature | SHT45, aspirated | exhaust fan PWM (cooling by room air), PTC heater | split-range PI: below setpoint → heater duty; above → fan duty; anti-windup; 10 s period | room + 2.5 K (lights on, full ventilation) to about 32 °C |
| Relative humidity | SHT45 | humidifier (up), exhaust fan (down, shares actuator with temperature) | hysteresis for humidifier; fan duty = max(temperature demand, humidity demand, CO₂ minimum) | about 54 % floor with mature crop in a 20 °C / 50 % room; upper limit set by condensation risk |
| PPFD | AS7341 monitor (calibrated) | LED PWM duty | open loop from calibration curve duty→PPFD per pod; AS7341 used for drift alarm, not feedback | 0-338 µmol m⁻² s⁻¹ at lid (simulated) |
| Photoperiod | host clock → node RTC | LED | schedule table on node, 1 min resolution, 5 min ramps | any |
| CO₂ | SCD30 | (ventilation only) | monitored; minimum ventilation 3 m³ h⁻¹ keeps drawdown < 100 ppm | ambient |
| Air movement | fan tach; anemometer at commissioning | mixing fan PWM | fixed duty (≈ 30 %) for 0.3-0.7 m s⁻¹ at canopy | - |
| Solution temperature | DS18B20 | none in v1 | monitored (root-zone temperature follows air temperature; reported as covariate) | - |
| pH, EC | Atlas EZO | manual dosing, logged (v1) | monitored + alarm bands; dosing channels reserved | - |
| Circulation | flow meter | pump | on continuously; alarm if flow < 50 % of commissioning value | ≈ 3 L min⁻¹ |
| Level / water use | float switch, reservoir load cell | peristaltic pump | top-up when float low for > 30 s; max 60 s per event and 500 mL per hour (flood guard) | - |

Why not Peltier or compressor cooling: at about 25 W sensible load per pod, ventilation with
20 °C room air needs only ~20 m³ h⁻¹ and adds no condensate handling. The cost is a hard site
requirement (ENV-01) and the inability to run pods below room temperature. Pods cannot
dehumidify below the room's dew point either. Both limits are stated in every protocol.

Cross-coupling that must be acknowledged: temperature, humidity and CO₂ share the exhaust fan.
A heat treatment at low ventilation raises humidity and lowers CO₂ unless the fan minimum is
respected; the heat-stress protocol therefore fixes VPD rather than RH and logs CO₂ as a covariate.

## Lighting design summary

Six Bridgelux EB Gen 3 4000 K strips above a 3 mm acrylic window: 223 µmol s⁻¹ emitted (estimate
from luminous flux), 84 W electrical at 100 %, 2.6 µmol J⁻¹ system efficacy; simulated mean
338 µmol m⁻² s⁻¹ over the grow area with min/mean 0.99 at plant positions (the simple model is
optimistic on uniformity; expect 0.85-0.95 measured). Control recipe: 74 % duty → 250 µmol m⁻² s⁻¹,
16 h, DLI 14.4 mol m⁻² d⁻¹, 1.0 kWh d⁻¹ per pod. PWM dimming keeps LED efficacy essentially
constant with duty. Full numbers: calculation report section 3.

## Control hierarchy, manual override, safety limits

```
 dashboard / experiment recipe ─┐
 digital-twin optimiser ────────┤ proposals (never direct actuation)
                                ▼
             host safety envelope (plantpulse.acquisition.safety)
             rejects or clamps: T 15-32 °C, RH 40-85 %, PPFD 0-300, photoperiod ≤ 20 h,
             DLI ≤ 17 unless the experiment explicitly raises it, rate limits
                                ▼  SET commands
             node firmware limits (same envelope compiled in, plus hard limits)
             interlocks: door open → gantry stop; leak → pumps off; over-temperature (36 °C air)
             → heater off + fan 100 %; comms loss > 120 s → hold last recipe, heater limited
                                ▼
             hardware: output-enable buffer, 45 °C heater cut-out, E-stop relays, fuses
```

Modes per pod: `AUTO` (recipe), `MANUAL` (operator sets actuator values from the dashboard; limits
still enforced; every change logged as an intervention), `SAFE` (all outputs off except
circulation, mixing fan and logging). A physical E-stop always wins. Setpoints coming from a model
are tagged `source = twin` and are only accepted in experiments whose protocol enables them.

## Alarms

Air T ± 3 °C from setpoint for 10 min; RH outside 40-90 % for 30 min; no flow; leak; reservoir
< 0.5 kg; pH outside 5.2-6.5; EC ± 0.4 mS cm⁻¹ from target; sensor silent > 60 s; image set missed;
LED rail power deviating > 10 % from expected for the commanded duty (strip or driver failure).
