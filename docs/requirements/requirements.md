# System requirements

Requirements are derived from the hypotheses (`docs/research/hypotheses.md`), not from what is
convenient to build. Each has a verification method: **A**nalysis, **I**nspection, **T**est
(see `docs/validation/validation_plan.md` for the test IDs).

## Science-driven requirements

| ID | Requirement | Rationale | Verify |
|----|-------------|-----------|--------|
| SCI-01 | ≥ 4 environmentally independent experimental units (pods), each with its own air volume, light source, nutrient solution and controller | Chamber-level treatments need unit replication; 4 allows a 4x4 Latin square | I |
| SCI-02 | 6 plants per pod (24 total) at 25 plants m⁻² | Sub-sampling to reduce unit-mean variance; realistic canopy competition | I |
| SCI-03 | Treatments assignable per pod by software, re-randomized each run | Balance pod effects over runs | T |
| SCI-04 | Every observation traceable to plant, unit, treatment, time, sensor, calibration, image, experiment | Auditability, dataset publication | T (VAL-DATA-02) |
| SCI-05 | No model output may be stored in a measured-data table; predictions carry `provenance = predicted` | Separation of measured and predicted values | I/T |
| SCI-06 | Blinding support: image file names and analysis tables expose pod/position codes, not treatment labels, until the analysis script joins the allocation table | Reduce analyst bias | I |

## Environment

| ID | Requirement | Verify |
|----|-------------|--------|
| ENV-01 | Room air ≤ 20 °C, 35-60 % RH (site requirement; pods cannot cool below room temperature) | T (site survey) |
| ENV-02 | Air temperature setpoint range room+3 °C to 32 °C; control ± 1.0 °C (95 % of minutes) | T VAL-ENV-01 |
| ENV-03 | RH 55-80 % controllable within ± 7 % RH when canopy load and room dew point allow; always monitored | T VAL-ENV-02 |
| ENV-04 | PPFD at lid plane 0-300 µmol m⁻² s⁻¹, dimmable in ≤ 1 % steps; uniformity min/mean ≥ 0.80 over plant positions | A + T VAL-LGT-01 |
| ENV-05 | Photoperiod programmable with 1 min resolution; light leak between pods and from room < 0.5 µmol m⁻² s⁻¹ during dark | T VAL-LGT-03 |
| ENV-06 | CO₂ monitored 400-2000 ppm, ± (30 ppm + 3 %); no enrichment in v1; ventilation keeps lights-on drawdown < 100 ppm below room | A + T |
| ENV-07 | Air speed at canopy 0.3-0.7 m s⁻¹ | T VAL-ENV-04 |
| ENV-08 | Nutrient solution: temperature, pH, EC continuously monitored; circulation ≥ 2 tub volumes h⁻¹; aeration | T VAL-WQ-01..03 |
| ENV-09 | Water consumption per pod resolved to ± 20 g d⁻¹ | T VAL-WQ-04 |
| ENV-10 | Electrical energy metered per pod for lighting (± 2 %) and for other loads; wall-plug energy metered for the rack | T VAL-PWR-01 |

## Imaging

| ID | Requirement | Verify |
|----|-------------|--------|
| IMG-01 | Top-view RGB of every plant at least every 2 h during the photoperiod | T VAL-DATA-01 |
| IMG-02 | Ground sample distance ≤ 0.2 mm px⁻¹ at lid plane | A + T |
| IMG-03 | Camera position repeatability ≤ 0.5 mm (1σ) at each station | T VAL-IMG-01 |
| IMG-04 | Fixed focus, fixed aperture, fixed exposure/gain/white balance, imaging under dedicated white LEDs with grow LEDs off; reference colour target in every frame | I + T VAL-IMG-02 |
| IMG-05 | Raw (DNG) + lossless-compatible processed image stored; UTC timestamp from NTP-disciplined clock; SHA-256 recorded | T |
| IMG-06 | Imaging hardware must not shade plants when parked (< 2 % PPFD change at any plant position) | T VAL-LGT-02 |

## Safety and operations

| ID | Requirement | Verify |
|----|-------------|--------|
| SAF-01 | All pod electronics SELV (≤ 48 V DC); mains only inside the PSU enclosure, on a GFCI-protected circuit | I |
| SAF-02 | Hardware E-stop removes actuator and LED power without removing logic/logging power | T VAL-SAF-01 |
| SAF-03 | Heater has an independent hardware thermal cut-out (45 °C) in series, independent of firmware | T VAL-SAF-02 |
| SAF-04 | Firmware enforces actuator limits and a communications watchdog: on loss of host for > 120 s the node continues the last valid schedule ("hold-last-recipe"), never free-runs a heater | T VAL-SAF-03 |
| SAF-05 | Model-based (digital twin) setpoints pass through a safety envelope checked on the host and again on the node; manual override always available | T VAL-CTL-02 |
| SAF-06 | Leak sensor in each pod tray and in the rack base; pumps stop on leak | T |
| OPS-01 | Daily checks completable in ≤ 15 min; all wet-side maintenance from the front door | I |
| OPS-02 | A pod can be removed/added without redesign (own node, own tub, three power feeds, one data link) | I |

## Cost and reproducibility

| ID | Requirement | Verify |
|----|-------------|--------|
| COST-01 | Target ≤ USD 1,600 per pod and ≤ USD 8,500 for the 4-pod facility including shared reference instruments, at single-quantity distributor prices | A (BOM) |
| REP-01 | Only catalogue parts, laser/CNC-cut sheet, and FDM-printable parts (≤ 220 x 220 mm bed) | I |
| REP-02 | All design sources open (CadQuery, KiCad, firmware, software), licensed CERN-OHL-P-2.0 / MIT / CC-BY-4.0 | I |
