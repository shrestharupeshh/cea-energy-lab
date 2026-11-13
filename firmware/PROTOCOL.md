# Node <-> host serial protocol (v1)

Transport: USB CDC serial, 115200 8N1, one message per line (`\n`). The simulated node
(`plantpulse.acquisition.sim_node`) speaks exactly the same protocol, so the whole host stack
is testable without hardware.

## Node -> host (JSON lines)

| `t` | Meaning | Fields |
|-----|---------|--------|
| `H` | hello at boot | `pod`, `fw`, sensor-present flags |
| `S` | sensor/actuator frame, 1 Hz | `pod`, `seq`, `ms` (node uptime), `mode` (0 SAFE, 1 AUTO, 2 MANUAL), `faults` (bit field), `air_t` C, `rh` %, `co2` ppm, `par_raw` counts, `sol_t`, `sol_t2` C, `ph`, `ec` uS/cm, `res_raw` counts, `flow_hz`, `tach0_hz`, `tach1_hz`, `led_w`, `act_w`, `led_wh`, `act_wh` (cumulative since boot), `u_heat`, `u_fan`, `u_mix`, `u_led` (duties), `pump`, `humid`, `topup`, `door`, `leak`, `flo`, `fhi`, `gpos` (steps) |
| `A` | acknowledgement | `id`, `ok`, `msg` |
| `E` | event | `ev` (`capture_done`, ...), `ms`, extras |

Values are raw engineering units from the sensor drivers. Calibration (PAR counts to PPFD,
load-cell counts to grams, pH/EC corrections) is applied on the host from the `calibration`
table so that raw values are always preserved.

Fault bits: 0 over-temperature, 1 air sensor stale, 2 host timeout, 3 leak, 4 door open,
5 E-stop, 6 top-up budget exhausted, 7 high-level float.

## Host -> node (ASCII, `VERB key=value ... id=N`)

| Verb | Keys | Effect |
|------|------|--------|
| `PING` | - | refreshes the comms watchdog |
| `TIME` | `epoch` (local-time seconds) | sets the node clock used for the photoperiod |
| `MODE` | `AUTO` / `MANUAL` / `SAFE` | operating mode |
| `SET` | `air_t_day`, `air_t_night`, `rh`, `led` (duty 0-1), `on`, `off` (minute of day), `ramp`, `mix`, `pump` | recipe setpoints; validated against compiled-in limits; applied atomically or rejected |
| `MAN` | `heater`, `fan`, `mix`, `led`, `pump`, `humid`, `topup` | manual actuator values (MANUAL mode only; interlocks still apply) |
| `MOVE` | `station` 0-3 (0 = park) | gantry move (homes first if needed) |
| `CAPTURE` | - | blank grow LEDs, imaging ring on, trigger camera node, restore |

Every command is acknowledged with an `A` frame carrying the same `id`. Unknown verbs, unknown
keys, non-numeric or out-of-range values are rejected as a whole.

## Safety behaviour implemented in `firmware/node/lib/core`

- Boot state SAFE; lights stay off until the host has set the time.
- Over-temperature (36 C): heater off, exhaust 100 %, LEDs off.
- Air sensor invalid or stale > 15 s: heater locked out.
- Host silent > 120 s: recipe continues, heater duty capped at 50 %.
- Leak or high-level float: pumps off. Door open: gantry disabled. E-stop sensed: outputs off.
- Top-up limited to 60 s per event and 240 s per hour.

Unit tests: `make -C firmware/node/test_host test` (runs on the host, no hardware).
