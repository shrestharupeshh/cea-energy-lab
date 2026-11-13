# Experimental program: pilot and Studies A-D

Read with `statistical_analysis_plan.md` (analysis), `crop_husbandry_sop.md` (how plants are
grown) and `manual_measurement_protocol.md` (ground truth). Treatment levels are chosen from
published lettuce response ranges (literature IDs refer to `docs/research/literature_matrix.csv`)
to be clearly sub-optimal but non-lethal, so that plants survive to harvest and yield
measurable contrasts.

## Common conditions (control recipe "C0")

| Variable | Control setpoint | Basis |
|----------|-----------------|-------|
| Cultivar | *Lactuca sativa* 'Rex' (butterhead, pelleted seed) | common hydroponic research/production cultivar, tipburn tolerant |
| PPFD at lid | 250 µmol m⁻² s⁻¹ | L18 |
| Photoperiod | 16 h (06:00-22:00 local) → DLI 14.4 mol m⁻² d⁻¹ | below DLI 17 ceiling, L34 |
| Air temperature | 23 °C light / 20 °C dark | L19, L34 |
| RH | 65-70 % (VPD ≈ 0.8-1.0 kPa) | tipburn management |
| CO₂ | ambient, monitored | no enrichment in v1 |
| Solution | EC 1.4 mS cm⁻¹, pH 5.8 (5.6-6.0), 18-23 °C, aerated | L34 |
| Air speed at canopy | 0.3-0.7 m s⁻¹ | tipburn management |
| Density | 25 plants m⁻² (6 per pod) | |
| Cycle | 12-14 d nursery (shared, outside pods) + 28 d in pod | |

Day 0 = transplant into pods. All pods run C0 from day 0 to the treatment onset day so that each
plant has a pre-treatment baseline.

## Pilot P0 - commissioning run (no hypothesis test)

Purpose: shake down hardware, husbandry and data pipeline with plants; tune controllers; tune
segmentation thresholds. Data are labelled `pilot` and are never pooled with study data.
Exit criteria: full 28-day cycle with H5b and H5c met in at least 3 of 4 pods.

## Pilot U1, U2 - uniformity trials (RQ5)

- Hypothesis: H5a-c.
- Independent variable: none (all pods C0). Classification factors: pod, run, position.
- Dependent variables: harvest shoot fresh/dry mass, leaf area, leaf number, tipburn score;
  environmental means and variability; data completeness.
- Experimental unit: pod-run (8 units). Subsamples: 6 plants each.
- Measurement frequency: sensors 1 min; images every 2 h in photoperiod; manual non-destructive
  measures twice weekly on all plants; destructive at day 28.
- Confounders: tier (upper/lower), proximity to room HVAC supply, seedling size at transplant
  (blocked: seedlings ranked by size and dealt across pods).
- Outputs: variance components for planning; pod-effect report; decision to proceed.

## Study A - environmental stress (feeds RQ1, RQ3)

- Hypothesis: each stress reduces harvest shoot dry mass relative to control; the image-derived
  relative growth rate diverges from control before the harvest difference is visible.
- Treatments (onset day 10, maintained to day 28):

| Code | Treatment | Level | Basis / safety |
|------|-----------|-------|----------------|
| C | Control | C0 | |
| L | Reduced light | PPFD 125 µmol m⁻² s⁻¹, same photoperiod (DLI 7.2) | linear region of light response; non-lethal (L17, L18) |
| H | Elevated temperature | 30 °C light / 26 °C dark air | supra-optimal for lettuce, below lethal; heater cut-out at 45 °C (L19) |
| N | Reduced nutrients | EC 0.4 mS cm⁻¹ (same pH), by solution exchange on day 10; control pods get a sham exchange with fresh C0 solution | mild-moderate deficiency over 18 d |

  Water deficit proper is not meaningful in DWC. An osmotic-stress arm (elevated EC with NaCl or
  PEG) is defined as optional Study A2 after A is complete; it is not part of the Latin square.
- Design: 4 x 4 Latin square (4 runs x 4 pods), each pod receives each treatment once.
- Independent variable: treatment. Dependent: as SAP section 2.
- Experimental unit: pod-run (n = 4 per treatment). Subsamples: 6 plants.
- Replication/sample size: see power analysis; adequate for ≥ 30 % dry-mass effects under planning
  variances; under-powered for ≤ 15 % effects - stated up front.
- Measurement frequency: sensors 1 min; images every 2 h (photoperiod) plus stereo offsets;
  manual leaf count, diameter, SPAD (if available), visual stress score by a rater blinded to
  treatment where feasible (H is not blindable at the pod, so rating is done from photographs) on
  days 0, 7, 10, 12, 14, 17, 21, 24, 28; destructive harvest at day 28.
- Confounders: root-zone temperature rises with H (measured, reported as part of the treatment);
  VPD changes with H (RH setpoint adjusted to hold VPD ≈ 1.0 kPa; residual difference reported);
  lower transpiration under L raises RH (controlled); operator handling order (randomized).

## Study B - growth trajectories and biomass ground truth (RQ2, RQ3)

- Hypotheses: H2a-c, H3a-b.
- Design: two dedicated runs with **serial destructive harvests**. Two PPFD levels are used to
  widen the size range: pods randomized to 150 or 250 µmol m⁻² s⁻¹ (2 pods each per run, swapped
  in the second run). On days 7, 14, 21 one plant per pod (pre-randomized position) is harvested,
  the remaining three plants at day 28. A harvested position receives a blank plug; the reduced
  competition is recorded as a covariate (`neighbours_present`).
- Ground truth per harvested plant: shoot fresh mass, shoot dry mass, root dry mass, leaf count,
  total leaf area (flatbed scan), maximum diameter, height.
- This yields 48 plants with destructive ground truth spanning the growth curve, each with its
  full image/environment history. Harvest-day data from Study A (96 plants) add end-of-cycle
  points and stress conditions for out-of-distribution tests.
- Experimental unit for model evaluation: pod-run; splits by run.
- Independent variables (prediction): image features, environment history, days after transplant.
- Dependent: shoot fresh/dry mass, leaf area.

## Study C - adaptive lighting (RQ4)

- Hypotheses: H4a-c.
- Treatments: **F** fixed C0 lighting; **A** adaptive: each day at lights-off the model-predictive
  controller (`plantpulse.optimization.mpc`) re-plans PPFD and photoperiod for the remaining days
  from the current vision-estimated plant state, minimizing predicted lighting energy subject to
  reaching the same day-28 target mass as F is predicted to reach, with constraints
  PPFD 100-300 µmol m⁻² s⁻¹, photoperiod 12-20 h, DLI ≤ 17 mol m⁻² d⁻¹, ≥ 4 h continuous dark,
  maximum day-to-day PPFD change 50 µmol m⁻² s⁻¹. All setpoints pass the safety envelope.
- Prerequisite: the twin's growth forecast must have met acceptance (VAL-DT-01) on Study B data.
  If it has not, Study C is postponed, or run with a pre-declared simple rule
  ("equal DLI over 20 h at lower PPFD") as the adaptive arm and reported as such.
- Design: 2 pods per treatment per run; ≥ 4 runs; balanced crossover over pods.
- Dependent: lighting energy (INA226, per pod), total pod energy, wall energy for the rack, shoot
  fresh/dry mass, tipburn, dry-matter content, water use.
- Confounders: the drivers are PWM-dimmed, so LED efficacy is nearly constant with dimming (only a
  small junction-temperature effect); any energy gain must therefore come from plant light-use
  efficiency, not from the LED. Heater energy rises when LEDs dim (reported separately; total
  energy is a secondary endpoint).

## Study D - multimodal stress prediction (RQ1)

No new plants: an analysis study on Study A data with its own pre-registered model comparison
(SAP section 5). If Study A2 (osmotic) is run, it becomes an external test set.

## Run calendar (indicative)

P0 (1 run) → U1, U2 (2 runs) → A1-A4 (4 runs) → B1-B2 (2 runs) → C1-C4 (4 runs): 13 runs x ~30
days ≈ 13 months of chamber time. Nursery overlaps the preceding run. Papers do not wait for the
full program (see `publications/publication_strategy.md`).
