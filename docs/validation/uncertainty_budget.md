# Measurement uncertainty budget (expected values, to be replaced by measured ones)

Standard uncertainties (k = 1). "Expected" numbers come from datasheets and the calibration
methods in `calibration_procedures.md`; they are planning values, not results. After VAL-SEN-xx
the measured calibration residuals replace column 2 and this file is regenerated.

| Quantity | Calibration residual | Reference | Resolution | Drift over 35 d | Combined (k=1) | Expanded (k=2) |
|----------|---------------------|-----------|------------|-----------------|----------------|----------------|
| Air temperature | 0.10 °C | 0.05 °C | 0.01 °C | 0.05 °C | 0.12 °C | 0.25 °C |
| Relative humidity | 1.0 %RH | 1.0 %RH (salt fixed point) | 0.01 | 0.5 %RH | 1.5 %RH | 3.0 %RH |
| CO₂ | 20 ppm + 2 % | 10 ppm | 1 ppm | 15 ppm | ≈ 30 ppm at 420 | ≈ 60 ppm |
| PPFD (AS7341 via Apogee transfer) | 3 % | 2.5 % (quantum sensor cal. + spectral error for white LED) | - | 2 % | 4.4 % | 9 % |
| DLI | as PPFD (time base negligible) | | | | 4.4 % | 9 % |
| Solution temperature | 0.10 °C | 0.05 °C | 0.06 °C | 0.05 °C | 0.14 °C | 0.3 °C |
| pH | 0.03 | 0.01 (buffers) | 0.001 | 0.05 between weekly checks | 0.06 | 0.12 |
| EC | 1.5 % | 1 % (standard) | 0.1 % | 2 % | 2.7 % | 5.4 % |
| Daily water use | 3 g | 0.5 g (weights) | 1 g | 10 g (thermal) | 11 g | 22 g |
| Lighting energy | 0.5 % | 1 % (wattmeter) | - | 0.5 % | 1.2 % | 2.4 % |
| Shoot fresh mass | 0.02 g | 0.01 g | 0.01 g | - | 0.03 g + handling loss (≤ 0.5 %) | - |
| Projected area (vision) | to be measured in VAL-IMG-03 / VAL-CV-02 | | | | - | - |

Method: `u_c = sqrt(sum u_i^2)`, rectangular distributions divided by sqrt(3) where the source is
a tolerance. Vision-derived traits get their uncertainty from the agreement study (limits of
agreement), not from a propagation model.
