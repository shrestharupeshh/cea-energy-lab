# Calibration procedures

Every calibration is entered through `MetaDB.add_calibration` (dashboard form or script): sensor
id, method, reference instrument and its certificate id, coefficients, residual SD, operator.
A new record closes the previous one; raw data are never altered, so processed data can always
be regenerated under any calibration history.

| Sensor | Interval | Procedure | Record |
|--------|----------|-----------|--------|
| SHT45 (T) | before each study, check after each run | All sensors + reference in the stirred box at 15/23/30 °C, 30 min each. Fit offset (gain fixed at 1 unless residuals show slope). | `{"type":"linear","gain":1,"offset":b}` |
| SHT45 (RH) | before each study | MgCl₂ and NaCl fixed points at 23 °C, 4 h. Two-point linear. | linear |
| SCD30 | before each study | Automatic self-calibration OFF. Forced recalibration in outdoor air (≈ 425 ppm, record the day's Mauna Loa value) after 5 min flush; check on soda-lime zero. | offset record + note |
| AS7341 → PPFD | at commissioning, every 30 days, after any LED/window change | Apogee sensor at the AS7341 position and at the 6 plant positions; duty 10-100 % in 10 steps, 5 min warm-up. Fit PPFD_plants_mean = gain x counts. Store per-position factors as pod metadata. | linear, per pod |
| Duty → PPFD table | same session | Used by `to_node_command`; `ppfd_full` per pod stored as a calibration of kind `led`. | linear |
| DS18B20 | yearly + check each study | Ice-point (crushed-ice slurry, 0.00 °C) and 25 °C bath vs reference. | linear |
| pH | weekly check, calibrate before each run | EZO 3-point (7.00, 4.00, 10.00) at 23 °C; slope must be 95-102 %; replace probe below 90 %. | EZO internal + record of slope |
| EC | before each run | Dry + 1413 µS cm⁻¹ single point (K 1.0), temperature compensation on. | record |
| Load cell | before each run | Tare empty cradle, then 1 kg and 5 kg check weights. | two_point |
| INA228 | at commissioning | Compare with reference wattmeter at 3 loads; correct shunt value. | linear |
| Camera geometry | at commissioning and after any lens touch | 20 checkerboard images → intrinsics/distortion (`cv2.calibrateCamera`); lock focus ring and aperture with threadlocker; record lens position mark. | `camera.intrinsics_json` |
| Camera colour | every run | Colour target under the imaging LEDs → 3 x 4 CCM (`color.fit_ccm`). Fixed exposure, gain 1.0, AWB off with fixed gains. | `camera.settings_json` |
| Gantry | at commissioning | Station positions adjusted so that fiducials sit at nominal pixels; steps/mm verified over 500 mm with a steel rule. | firmware constants + record |
| Balance | each weighing session | 100 g and 200 g check weights. | session log |

Reference instruments (shared): quantum sensor with current manufacturer calibration (recalibrate
every 2 years), reference thermometer with traceable certificate, class M1 check weights,
buffer and conductivity standards within expiry (lot numbers recorded).
