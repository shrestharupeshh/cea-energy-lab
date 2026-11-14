# Build and commissioning guide (Phases 7-8: requires physical work)

Nothing in this guide has been executed yet. It is the plan a builder follows; deviations and
photos go in `docs/manufacturing/build_log.md` (create at first build).

## 0. Before ordering

1. Site check: room that holds ≤ 20 °C year-round, 15 A GFCI circuit, floor drain or spill tray,
   Wi-Fi or Ethernet, bench for nursery and harvest, access to a balance and drying oven.
2. Resolve the `verify` items in `bom.csv` and the five review items in
   `docs/architecture/electronics_architecture.md` section 5.
3. Order ONE pod's parts first. Build and commission it before ordering the other three.

## 1. Fabrication

| Step | Input | Tool |
|------|-------|------|
| Cut extrusion | `hardware/mechanical/output/bom_mechanical.csv` | mitre saw with non-ferrous blade, or order cut to length |
| Cut panels, lid, window, LED plate | `output/dxf/` | CNC router / laser (acrylic, PVC only on a router) / hand tools |
| Print parts | `output/3mf/` | FDM, PETG, 0.2 mm; light traps in matte black |
| PCB | `hardware/electrical/pcb/plantpulse_node/fab/` | order; solder low parts first; sockets for all modules |
| Fiducial bars | print 8 ArUco markers (DICT_4X4_50 ids 0-7, 20.0 mm) on matte label stock | measure printed size with a caliper; must be 20.0 ± 0.1 mm |

## 2. Assembly order (one pod)

1. Base ring, columns, tub cross-members; square within 1 mm on diagonals.
2. Floor panel, back/side/partition panels into slots; mid ring; gantry beam.
3. Rail, carriage, motor, idler, belt, home switch; check free travel by hand.
4. Camera mount, HQ camera, lens (set f/8, focus at 380 mm on a target, lock), Pi Zero, LED ring.
5. Window, LED plate with strips (thermal tape + M3 screws), LED bay fan, top ring, top cover.
6. Fans, light traps, heater with cut-out wired in series, humidifier, sensor shield.
7. Service bay: shelf, load cell, cradle, reservoir; pump, flow meter, peristaltic pump; drip tray.
8. Node enclosure, harness (label both ends of every cable), blade-fuse feeds.
9. Tub, lid, probes, tubing, air stone. Fiducial bars at lid height, 40 mm from the lid edges.
10. Doors, gaskets, magnetic catches, door switch.

## 3. Electrical bring-up (no plants, no water)

1. PCB alone on a bench supply (24 V, 0.2 A limit): check 5 V, 5 V_CAM, 12 V rails before
   inserting any module.
2. Insert ESP32; flash firmware (`pio run -t upload` in `firmware/node`); read the hello frame.
3. Connect sensors one at a time; confirm each appears in the hello flags and in `S` frames.
4. Outputs: with loads disconnected, check that every output is off at reset and until the
   firmware asserts the output enable; then test each output in MANUAL mode with its load.
5. E-stop, door switch, leak sensor, float switches, heater cut-out (VAL-SAF-01..04).
6. Gantry homing, station moves, capture sequence (grow LEDs blank, ring on, image arrives).

## 4. Wet commissioning

Fill with RO water; leak test 48 h (VAL-WQ-02); flow and water-accounting tests (VAL-WQ-01, -04).

## 5. Calibration and acceptance

Follow `docs/validation/calibration_procedures.md`, then the validation plan sections A-F in
order. Enter results in `acceptance_criteria.csv`. Do not start pilot P0 with open failures in
sections A, B, C or F.

## 6. Software installation (central computer)

```
git clone <repo> && cd cea-energy-lab
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dashboard,hardware,dev]"
pytest                                   # must pass
python -m plantpulse.acquisition.daemon --experiment EXP-2027-P0 --ports /dev/ttyACM0,...   (systemd unit recommended)
streamlit run software/plantpulse/dashboard/app.py
```
Camera node image: Raspberry Pi OS Lite, `picamera2`; capture script and sync service are
**not yet written** (see open items in `docs/phases/PHASE_LOG.md`).

## 7. Backups (3-2-1)

Raw data and the metadata database are copied nightly to two external SSDs (alternating) with
`rsync --checksum` and weekly to an off-site/cloud location with `restic`. A restore drill is an
acceptance test (VAL-DATA-05). Raw files are written read-only and never edited.
