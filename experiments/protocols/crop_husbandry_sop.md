# Crop husbandry SOP (lettuce, DWC pods)

## Nursery (days −14 to 0, outside the pods)

1. Sow pelleted 'Rex' seed, one per 25 mm stone-wool cube (pre-soaked in pH 5.8, EC 0.6 mS cm⁻¹
   solution). Sow 2x the number required (48 for 24 positions).
2. Germinate under a humidity dome at 20-22 °C, 150 µmol m⁻² s⁻¹, 16 h. Remove dome at emergence.
3. Sub-irrigate with EC 1.0 solution from day −10. Log nursery temperature and PPFD (portable
   logger); nursery conditions are recorded as run-level metadata.
4. Day 0 selection: discard the largest and smallest 15 %; rank the rest by projected area
   (photograph the tray under the nursery camera); deal ranked seedlings across pods and positions
   with `plantpulse.stats.design.allocate_seedlings` (stratified randomization).

## Pod preparation (day −2 to 0)

1. Clean tub, lid, net pots, tubing: detergent, rinse, 0.5 % sodium hypochlorite 10 min, triple
   rinse with RO water. Wipe chamber walls with 70 % ethanol.
2. Calibrate pH (pH 4.00 / 7.00 / 10.00 buffers) and EC (1413 µS cm⁻¹ and dry point) probes;
   record through the dashboard (`calibration` table). Verify DS18B20 against the reference
   thermometer if > 30 days since the last check.
3. Fill tub with 26 L solution: RO water + two-part hydroponic fertilizer (e.g. Jack's 5-12-26 +
   calcium nitrate) to EC 1.4 mS cm⁻¹; adjust to pH 5.8 with dilute phosphoric acid / potassium
   hydroxide. Record product lot numbers and masses.
4. Start circulation and aeration; fill the top-up reservoir with RO water (C0) and tare.
5. Run the pre-flight check from the dashboard (sensors alive, fans, pump flow, gantry homing,
   test image, door switch, E-stop test).

## Daily (≤ 15 min for 4 pods)

- Dashboard review: alarms, environment traces, images captured, top-up reservoir level.
- Visual check through the window; open the door only if needed.
- pH: if outside 5.6-6.0, adjust to 5.8 with ≤ 2 mL increments of dilute acid/base; log as an
  intervention with volume. EC: if drift > ± 0.2 mS cm⁻¹ from target, correct with stock or RO
  water; log. Automatic dosing is an upgrade; v1 is manual-and-logged by design so that every
  correction is an explicit record.
- Refill top-up reservoir when < 1 L; the software logs refill events from the load cell step.

## Weekly

- Check pH probe against pH 7.00 buffer (accept ± 0.1; else recalibrate and flag the preceding
  interval). Check EC probe in 1413 µS cm⁻¹ standard (accept ± 3 %).
- Clean camera window/lens if dusty; wipe LED window.
- Inspect roots of one randomly chosen plant per pod (colour, smell) - log.

## Pests and disease

- Sticky card in each pod, inspected weekly. No pesticides inside a study; a pod with a confirmed
  pest/pathogen is flagged and handled per the SAP exclusion rules.

## Harvest and turnaround

- Harvest per `manual_measurement_protocol.md`. Drain solution, record remaining volume, sample
  50 mL for optional ion analysis. Clean as above. Export the run's raw data bundle and verify
  the backup before wiping any local buffers.
