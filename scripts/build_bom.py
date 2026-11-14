"""Facility bill of materials with sourcing data -> docs/manufacturing/bom.csv and cost_estimate.md.

PRICES ARE ESTIMATES (single-quantity US list prices as remembered at the time of writing, 2026-11)
and were NOT checked against live distributor listings. Availability and lead time are deliberately
not filled in: check them at order time. `verify` flags part numbers that must be confirmed.
"""
import csv
from collections import defaultdict

from plantpulse.config import REPO_ROOT

# (id, subsystem, description, manufacturer, mpn, supplier, qty_per_pod, qty_facility_shared, unit_price_est, origin_note, alternative, verify)
B = [
 ("ST-01", "Structure", "2020 T-slot extrusion, cut to length (18.0 m per pod; see bom_mechanical.csv)", "Misumi / 80-20 / generic", "HFS5-2020 (Misumi) cut lengths", "Misumi USA", 18.0, 0, 7.5, "Misumi: Japan/Vietnam; distributed from US", "McMaster 5537T101; 80/20 20-2020", "per metre"),
 ("ST-02", "Structure", "Corner bracket 2020 + M5 T-nuts + M5x8 BHCS (set per joint)", "generic", "-", "McMaster-Carr / Misumi", 72, 0, 0.9, "unknown", "Misumi HBLFSN5", ""),
 ("ST-03", "Structure", "Expanded PVC sheet 5 mm white 1220x2440 (panels)", "Sintra / Komatex", "-", "local plastics supplier / TAP Plastics", 1.2, 0, 62.0, "US-made brands exist (verify)", "6 mm corrugated PP (less rigid)", "sheets per pod"),
 ("ST-04", "Structure", "Expanded PVC 6 mm matte black 600x400 (lid) + 3 mm white (fiducial bars)", "generic", "-", "local plastics supplier", 1, 0, 14.0, "", "", ""),
 ("ST-05", "Structure", "Cast acrylic 3 mm clear 840x540 (LED window)", "generic", "-", "local plastics supplier / McMaster 8560K", 1, 0, 28.0, "", "polycarbonate (lower PAR transmittance, scratches)", ""),
 ("ST-06", "Structure", "Aluminium sheet 5052 3 mm 780x480 (LED heat spreader)", "generic", "-", "McMaster-Carr 89015K / local metal supplier", 1, 0, 45.0, "", "", ""),
 ("ST-07", "Structure", "Hinges, magnetic catches, EPDM door gasket, cable glands, levelling feet", "generic", "-", "McMaster-Carr", 1, 0, 38.0, "", "", "kit"),
 ("ST-08", "Structure", "PETG filament for printed parts (~0.6 kg per pod)", "generic", "-", "any", 0.6, 0, 22.0, "", "ASA", "per kg"),
 ("HY-01", "Hydroponics", "Euro container 600x400x170 mm, opaque PP, food grade", "Auer Packaging", "EG 64/17 HG", "Auer / US reseller", 1, 0, 24.0, "Germany", "any 600x400x170 Euro-norm container (check lid fit)", "verify"),
 ("HY-02", "Hydroponics", "Net pot 2 inch (pack of 25)", "generic", "-", "hydroponics retailer", 0.25, 0, 9.0, "", "", ""),
 ("HY-03", "Hydroponics", "Circulation pump 12 V brushless, ~4 L/min, 3 m head", "generic (DC30A class)", "DC30A-1230", "Amazon / AliExpress", 1, 0, 13.0, "China; no traceable datasheet", "Topsflo TL-B03 (traceable datasheet)", "verify curve"),
 ("HY-04", "Hydroponics", "Peristaltic pump 12 V, silicone tube", "Adafruit (generic OEM)", "1150", "Adafruit", 1, 0, 25.0, "China", "Kamoer NKP", ""),
 ("HY-05", "Hydroponics", "Hall flow meter 0.3-6 L/min", "generic", "YF-S401", "Amazon / Seeed", 1, 0, 8.0, "China", "Gems RFS (industrial)", ""),
 ("HY-06", "Hydroponics", "Float switch, PP, vertical (x2) + leak sensor pad", "generic", "-", "Amazon / DigiKey", 1, 0, 14.0, "", "", "set"),
 ("HY-07", "Hydroponics", "Top-up reservoir 5 L HDPE jerrycan", "generic", "-", "US Plastic Corp", 1, 0, 8.0, "USA (verify)", "", ""),
 ("HY-08", "Hydroponics", "Silicone tubing 8 mm ID, barbed fittings, bulkheads, air stone, check valve", "generic", "-", "McMaster-Carr / US Plastic", 1, 0, 30.0, "", "", "kit"),
 ("HY-09", "Hydroponics", "Aquarium air pump, 4 outlets (shared by rack)", "Hydrofarm", "Active Aqua AAPA15L", "Hydrofarm dealer", 0, 1, 30.0, "China", "", "verify"),
 ("LT-01", "Lighting", "LED strip 560 mm 4000 K CRI80, 2675 lm @ 700 mA", "Bridgelux", "BXEB-L0560Z-40E2000-C-C3", "DigiKey / Arrow", 6, 0, 9.5, "designed USA, made in China (verify)", "Samsung LT-Q562B (verify electrical fit)", ""),
 ("LT-02", "Lighting", "Constant-current buck LED driver 700 mA, PWM dim, wired", "Mean Well", "LDD-700HW (or NLDD-700HW)", "DigiKey / Mouser / TRC", 3, 0, 9.0, "Taiwan/China", "LDD-700H is marked obsolete at DigiKey: confirm successor", "verify"),
 ("LT-03", "Lighting", "48 V supply 600 W (shared)", "Mean Well", "LRS-600-48", "DigiKey / Mouser", 0, 1, 75.0, "Taiwan/China", "HLG-600H-48A (sealed)", ""),
 ("LT-04", "Lighting", "Imaging LED ring, 5000 K high-CRI, 12 V, diffuser", "generic", "-", "Amazon / Waveform Lighting strip", 1, 0, 16.0, "Waveform: designed USA", "", ""),
 ("AIR-01", "Air", "Fan 80x25 mm 12 V PWM", "Noctua", "NF-A8 PWM", "Amazon / Newegg", 3, 0, 18.0, "Taiwan/China", "Sunon MF80251V1 PWM (DigiKey)", ""),
 ("AIR-02", "Air", "PTC fan heater 24 V 100 W", "generic", "-", "Amazon", 1, 0, 16.0, "China; no traceable datasheet", "DBK Cirrus 25 (industrial, traceable)", "verify"),
 ("AIR-03", "Air", "Bimetal thermostat 45 C normally closed, 10 A (heater cut-out)", "Cantherm / Sensata", "KSD301 45C NC", "DigiKey", 1, 0, 4.0, "", "", ""),
 ("AIR-04", "Air", "Ultrasonic mist maker ~150 mL/h, 24 V, with float + 30 mm fan for sensor shield", "generic", "-", "Amazon", 1, 0, 18.0, "China", "", ""),
 ("SN-01", "Sensors", "SHT45 temperature/humidity breakout", "Adafruit (Sensirion sensor)", "5665", "Adafruit / DigiKey", 1, 0, 12.5, "sensor Switzerland; board assembled USA", "SHT85 (Sensirion, DigiKey)", ""),
 ("SN-02", "Sensors", "SCD30 NDIR CO2 breakout", "Adafruit (Sensirion sensor)", "4867", "Adafruit / DigiKey", 1, 0, 59.0, "sensor Switzerland; board assembled USA", "SCD41 (Adafruit 5190, lower accuracy)", ""),
 ("SN-03", "Sensors", "AS7341 10-channel spectral sensor breakout + PTFE diffuser", "Adafruit (ams OSRAM sensor)", "4698", "Adafruit / DigiKey", 1, 0, 16.0, "board assembled USA", "Apogee SQ-520 per pod (research grade, ~USD 400)", ""),
 ("SN-04", "Sensors", "DS18B20 waterproof probe (x2)", "Adafruit (Maxim/ADI sensor)", "381", "Adafruit / DigiKey", 2, 0, 10.0, "", "", ""),
 ("SN-05", "Sensors", "EZO-pH circuit + isolated carrier + lab-grade pH probe", "Atlas Scientific", "EZO-pH + ISCCB-2 + ENV-40-pH", "Atlas Scientific / DigiKey", 1, 0, 165.0, "USA (New York)", "DFRobot Gravity pH V2 (not isolated, lower grade)", "verify kit numbers"),
 ("SN-06", "Sensors", "EZO-EC circuit + isolated carrier + K1.0 probe", "Atlas Scientific", "EZO-EC + ISCCB-2 + ENV-40-EC-K1.0", "Atlas Scientific / DigiKey", 1, 0, 215.0, "USA (New York)", "DFRobot Gravity EC", "verify kit numbers"),
 ("SN-07", "Sensors", "Bar load cell 5 kg + NAU7802 24-bit ADC breakout", "SparkFun / Adafruit", "SEN-14729 + Adafruit 4538", "SparkFun / Adafruit", 1, 0, 19.0, "boards assembled USA", "HX711 (noisier)", ""),
 ("SN-08", "Sensors", "INA228 85 V power monitor breakout (x2)", "Adafruit (TI sensor)", "5832", "Adafruit / DigiKey", 2, 0, 10.0, "board assembled USA", "", "verify"),
 ("SN-09", "Sensors", "Door reed switch, cables, JST-XH pigtails", "generic", "-", "DigiKey / Adafruit", 1, 0, 15.0, "", "", "kit"),
 ("IM-01", "Imaging", "Raspberry Pi HQ Camera (IMX477, CS mount)", "Raspberry Pi", "SC0261", "PiShop.us / Adafruit / SparkFun", 1, 0, 54.0, "UK (Wales)", "Arducam IMX477", ""),
 ("IM-02", "Imaging", "6 mm CS-mount lens", "Raspberry Pi / CGL", "SC0123", "PiShop.us / Adafruit", 1, 0, 27.0, "China", "Arducam 6 mm; a 10 MP-rated lens for full sensor resolution", ""),
 ("IM-03", "Imaging", "Raspberry Pi Zero 2 W + 32 GB endurance microSD + camera ribbon", "Raspberry Pi", "SC0510", "PiShop.us / Adafruit", 1, 0, 30.0, "UK (Wales)", "Pi 3A+", ""),
 ("IM-04", "Imaging", "Linear rail MGN12, 700 mm, with MGN12H block", "HIWIN (or generic)", "MGN12H1R700", "Amazon / Misumi (SSEBZ)", 1, 0, 32.0, "HIWIN: Taiwan; generic: China", "", ""),
 ("IM-05", "Imaging", "NEMA17 stepper 42x40 mm 1.8 deg", "StepperOnline", "17HS4401S", "StepperOnline / Amazon", 1, 0, 13.0, "China", "Pololu 2267", ""),
 ("IM-06", "Imaging", "TMC2209 SilentStepStick", "Trinamic / BigTreeTech", "TMC2209 v1.3", "DigiKey / Amazon", 1, 0, 8.0, "", "Pololu DRV8825 (pin compatible; set MS pins)", ""),
 ("IM-07", "Imaging", "GT2 belt 6 mm (2 m), 20T pulley, idler, microswitch, drag cable", "generic", "-", "Amazon / Pololu", 1, 0, 14.0, "", "", "kit"),
 ("IM-08", "Imaging", "Colour reference card (24 patch, small format)", "Calibrite", "ColorChecker Classic Mini", "B&H", 1, 0, 60.0, "", "printed + spectro-measured card", ""),
 ("EL-01", "Electronics", "ESP32-S3-DevKitC-1 (N8R2)", "Espressif", "ESP32-S3-DevKitC-1-N8R2", "DigiKey / Mouser", 1, 0, 15.0, "China", "", ""),
 ("EL-02", "Electronics", "Node carrier PCB PP-E-001, 175x120 mm, 2-layer, 2 oz (5 pcs)", "any fab (OSH Park USA / JLCPCB)", "PP-E-001 rev A", "OSH Park / JLCPCB", 0.25, 0, 60.0, "fab-dependent", "", "per 5 boards"),
 ("EL-03", "Electronics", "PCB parts (see plantpulse_node_bom.csv): TRACO TSR x3, MOSFETs, MCP23017, 74HCT541, connectors, passives", "various", "-", "DigiKey / Mouser", 1, 0, 68.0, "", "", "kit"),
 ("EL-04", "Electronics", "IP65 ABS enclosure 200x120x75", "Hammond", "1554 series (size to PCB)", "DigiKey / Mouser", 1, 0, 24.0, "Canada (verify)", "Bud Industries (USA)", "verify size: PCB is 175x120"),
 ("EL-05", "Electronics", "Wiring: AWG16/18/20 silicone wire, ferrules, WAGO 221, heat-shrink", "generic", "-", "DigiKey / McMaster-Carr", 1, 0, 25.0, "", "", "kit"),
 ("PW-01", "Power (shared)", "24 V supply 600 W", "Mean Well", "LRS-600-24", "DigiKey / Mouser", 0, 1, 70.0, "Taiwan/China", "", ""),
 ("PW-02", "Power (shared)", "Enclosure, IEC inlet with fuse + switch, DIN rail, blade fuse block, E-stop, 2 x 40 A relays, terminal blocks", "various", "-", "DigiKey / McMaster-Carr", 0, 1, 160.0, "", "", "kit"),
 ("PW-03", "Power (shared)", "Smart plug with energy metering (local API)", "Shelly", "Plus Plug US", "Shelly USA", 0, 1, 22.0, "", "Kill-A-Watt P4460 (manual reading)", ""),
 ("CP-01", "Computing (shared)", "Raspberry Pi 5 8 GB + active cooler + 27 W PSU + NVMe HAT + 500 GB NVMe", "Raspberry Pi", "SC1112", "PiShop.us / Adafruit", 0, 1, 190.0, "UK (Wales)", "", ""),
 ("CP-02", "Computing (shared)", "Powered USB hub (7 port), cables, UPS for the Pi, backup SSD x2", "generic", "-", "Amazon / B&H", 0, 1, 190.0, "", "", "kit"),
 ("RF-01", "Reference instruments (shared)", "Quantum PAR meter, full spectrum", "Apogee Instruments", "MQ-500", "Apogee", 0, 1, 565.0, "USA (Utah)", "LI-COR LI-190R + LI-250A", ""),
 ("RF-02", "Reference instruments (shared)", "Reference thermometer +/-0.1 C traceable; hot-wire anemometer; handheld pH/EC meter", "various", "-", "Thermco / Extech / Hanna", 0, 1, 520.0, "", "", "set"),
 ("RF-03", "Reference instruments (shared)", "Balance 620 g x 0.01 g; check weights; buffers and standards; salts for RH points", "various", "-", "lab supplier", 0, 1, 520.0, "", "university shared balance", "set"),
 ("CN-01", "Consumables (per year)", "Seed, stone-wool cubes, two-part fertiliser, pH adjusters, RO water, cleaning", "various", "-", "Johnny's / hydroponics retailer", 0, 1, 250.0, "", "", "estimate"),
]
N_PODS = 4
rows, sub = [], defaultdict(lambda: [0.0, 0.0])
for (i, s, d, m, mpn, sup, qp, qs, price, origin, alt, ver) in B:
    pod_cost, shared_cost = qp * price, qs * price
    sub[s][0] += pod_cost
    sub[s][1] += shared_cost
    rows.append({"id": i, "subsystem": s, "description": d, "manufacturer": m, "mpn": mpn, "supplier": sup, "qty_per_pod": qp, "qty_shared": qs,
                 "unit_price_usd_est": price, "ext_per_pod_usd": round(pod_cost, 2), "ext_shared_usd": round(shared_cost, 2),
                 "price_basis": "estimate 2026-11, not verified online", "availability_lead_time": "check at order",
                 "origin_note": origin, "alternative": alt, "verify": ver})
out = REPO_ROOT / "docs" / "manufacturing"
with open(out / "bom.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
pod = sum(v[0] for v in sub.values())
shared = sum(v[1] for v in sub.values())
total = N_PODS * pod + shared
md = ["# Prototype cost estimate", "", "Generated by `scripts/build_bom.py` from the table in that script (mirrored in `bom.csv`).",
      "**All prices are estimates** recalled at the time of writing and not checked against live listings; expect +/- 20 %.",
      "Shipping, tax, tools (3D printer, soldering station, saw) and labour are excluded.", "",
      "| Subsystem | Per pod (USD) | Shared, once (USD) |", "|---|---|---|"]
for s, (a, b) in sub.items():
    md.append(f"| {s} | {a:,.0f} | {b:,.0f} |")
md += [f"| **Total** | **{pod:,.0f}** | **{shared:,.0f}** |", "",
       f"- One pod: about USD {pod:,.0f}. Requirement COST-01 target: <= 1,600 per pod -> {'met' if pod <= 1600 else 'NOT met'} on these estimates.",
       f"- Four-pod facility: 4 x {pod:,.0f} + {shared:,.0f} = **USD {total:,.0f}** (target <= 8,500 -> {'met' if total <= 8500 else 'NOT met'}).",
       f"- With a 15 % contingency: USD {total * 1.15:,.0f}.",
       "", "## Where the money goes", "",
       "- Water-quality instrumentation (isolated pH + EC) is about a quarter of each pod. A 'lite' pod with a shared handheld meter",
       "  and daily manual readings saves about USD 380 per pod at the cost of continuous root-zone records.",
       "- Reference instruments are a one-off shared cost and are what make the low-cost sensors defensible.",
       "- Structure cost is dominated by extrusion; buying 3 m bars and cutting in-house roughly halves it.", ""]
(out / "cost_estimate.md").write_text("\n".join(md))
print("\n".join(md[6:22]))
