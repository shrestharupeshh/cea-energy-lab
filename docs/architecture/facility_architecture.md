# Facility architecture: trade studies and selected layout

## 1. Independent compartments (A) vs shared environment with treatment groups (B)

| Criterion | A: independent pods | B: one chamber, treatment groups inside |
|-----------|--------------------|------------------------------------------|
| Experimental unit for light / temperature / humidity / CO₂ treatments | Pod-run. True replication possible | The whole chamber. Plants are subsamples; n = 1 per run. Treatments are confounded with position, shading and airflow |
| Root-zone treatments (EC, pH, solution temperature) | Pod-run (tub) | Possible with separate tubs; air environment shared (acceptable for these factors only) |
| Cross-talk | Small, measurable (light leak, heat through walls) | Inherent: light spill, shared air, shared humidity |
| Cost / complexity | N x (controller, LEDs, fans, sensors) | Lower: one air system, one controller |
| Failure impact | One pod | Entire experiment |
| Energy metering per treatment | Direct | Requires allocation assumptions |
| Uniformity trial meaning | Tests pod-to-pod equivalence directly | Tests positional gradients only |

**Decision: Architecture A**, four pods, because RQ1, RQ3 and RQ4 all manipulate aerial
environment or lighting. Under B those experiments would be pseudoreplicated regardless of how
many plants were grown. B remains available *inside* a pod for future root-zone-only work
(e.g. two half-size tubs), but is not used for the planned studies.

Honest limits of A as built: n = 4 units per run. Statistical replication comes from repeated
runs with re-randomized treatment-to-pod assignment (blocks in time). Pods share the room, so the
room is a common background that is logged and enters the models as a run-level covariate.

## 2. Pod concept

One pod = one module on a 2020 aluminium frame, 1040 W x 540 D x 880 H mm:

```
        +--------------------------------------+-----------+
  880   | LED bay: 4 x 560 mm strips on Al     |           |
        | plate, own cooling fan (room air)    | node box  |
  763   +========== acrylic window ============+ (IP65)    |
        | gantry rail on back wall, camera arm |           |
        |   parked at x<100 during growth      | top-up    |
        |                                      | reservoir |
        |   canopy zone 539 mm clear           | on load   |
        |   T/RH/CO2 aspirated shield          | cell      |
  201   +--[ o   o   o ]--lid, 6 net pots------+           |
        |  [ o   o   o ]  DWC tub 600x400x170  | circ pump |
   20   +--------------------------------------+-----------+
          growth chamber 800 x 500              service bay 200
```

- **Root zone**: deep-water-culture tub (Euro container), about 26 L at 120 mm depth, opaque,
  with matte-black lid carrying six 2-inch net pots on a 200 mm pitch (25 plants m⁻²).
  DWC is chosen over NFT/ebb-flow for thermal and chemical inertia, tolerance to pump failure,
  and simple water accounting. A small pump recirculates through a flow meter and a return spray
  bar; aeration comes from an air stone fed by a rack-level air pump.
- **Water accounting**: a float switch and a peristaltic pump hold the tub level constant from a
  5 L top-up reservoir that sits on a load cell. Reservoir mass loss = pod water uptake +
  evaporation (the tub is lidded; evaporation is characterized with a plant-free blank run).
- **Light**: four Bridgelux EB Gen 3 560 mm strips, two NLDD-700H constant-current drivers,
  PWM dimmed. LEDs sit above an acrylic window so their convective heat never enters the chamber.
- **Air**: one PWM exhaust fan (light-trapped inlet and outlet), one internal mixing fan, a 100 W
  24 V PTC heater with hardware cut-out, an ultrasonic humidifier. Cooling is by ventilation with
  conditioned room air, so the room must be at or below 20 °C (ENV-01).
- **Sensing**: SHT45 (T/RH) + SCD30 (CO₂) in a fan-aspirated radiation shield at canopy height,
  AS7341 spectral sensor as a PAR monitor (cross-calibrated to a reference quantum sensor), DS18B20
  in solution, Atlas EZO pH and EC on isolated carriers, flow meter, float switches, leak sensor,
  INA226 power monitors on the LED and actuator rails.
- **Imaging**: see section 3.
- **Control**: one ESP32-S3 node board per pod (deterministic sensing/actuation, safety limits),
  USB to the central Raspberry Pi 5.

## 3. Imaging architecture trade study

Scores 1 (poor) to 5 (good). Weights reflect that repeatability and image geometry drive RQ2.

| Option | Repeatability (x3) | Image quality / GSD (x3) | Cost for 4 pods (x2) | Shading / intrusion (x2) | Complexity (x1) | Weighted |
|--------|----|----|----|----|----|----|
| One fixed overhead camera per pod (wide lens) | 5 | 2 (oblique view of outer plants, 0.25 mm/px, lens distortion) | 5 | 2 (camera permanently over canopy centre) | 5 | 38 |
| Three fixed cameras per pod | 5 | 4 | 2 (12 cameras, multiplexing) | 1 | 3 | 36 |
| **Single-axis belt gantry per pod, one camera, three stations** | 4 (homed stepper, ≤ 0.1 mm) | 5 (near-nadir, 0.13 mm/px, known stereo baseline for height) | 4 | 5 (parks outside the canopy) | 3 | **48** |
| Robotic arm serving all pods | 3 | 5 | 1 | 4 | 1 (and breaches pod isolation) | 34 |

**Decision: single-axis gantry per pod.** A rail on the back wall carries a 250 mm cantilever arm
with a Raspberry Pi HQ camera (IMX477, 6 mm lens at f/8) looking down from 500 mm above the lid.
Each station sees one column of two plants near nadir. Two additional exposures offset ± 30 mm
from each station give a calibrated stereo baseline for canopy height (experimental feature, see
`software/plantpulse/computer_vision/height.py`). The arm parks at x = 40 mm, outside the plant
footprint. A Raspberry Pi Zero 2 W rides on the carriage so the fragile CSI ribbon never flexes;
only a 4-wire power/trigger cable is in the drag loop.

Imaging illumination: a diffuse 5000 K high-CRI LED ring on the carriage; the node turns the grow
LEDs off for about 3 s per exposure so that exposure and colour are independent of treatment PPFD.
Imaging is restricted to the photoperiod to avoid night-break effects.

## 4. Computing platform trade study

| Platform | Role fit | Decision |
|----------|---------|----------|
| Raspberry Pi 5 (8 GB, NVMe) | Database, dashboard, pipelines, classical CV, tree models; CPU inference of small CNNs for 24 plants is seconds per cycle | **Central computer** |
| NVIDIA Jetson Orin Nano | Needed only for on-line deep models at video rate; training is done off-line on a workstation | Not justified in v1; drop-in later |
| Raspberry Pi Zero 2 W | picamera2 full manual control + DNG raw for the HQ camera | **Camera node, one per pod** |
| ESP32-S3 (DevKitC-1) | Hard-real-time enough for 1 Hz sensing, 25 kHz fan PWM, stepper pulses via RMT; dual core; USB CDC | **Pod controller** |
| STM32 | Better ADC/timers, no benefit here; weaker hobby-reproducibility | Alternative |
| Arduino Mega | Insufficient timers/memory, 5 V logic | Rejected |

The microcontroller owns safety: limits, interlocks and schedules run on the node and survive a
host crash (SAF-04). The host never drives an actuator pin directly.

## 5. Rack layout and modular growth

Baseline: 2 x 2 pods on a common rack, 2080 W x 540 D x ~1860 H mm including levelling feet. A
rack-side power enclosure holds the 24 V and 48 V supplies, E-stop relay and per-pod fusing.
Adding pods: bolt on another column (two pods), add one USB port and three fused feeds. Software
discovers nodes by their reported `pod_id`.

Position effects in the rack (upper vs lower tier, left vs right) are part of the pod effect and
are handled by re-randomization and by the uniformity trials.

CAD: `hardware/mechanical/cad/`. Calculations: `hardware/mechanical/calculations/`.
