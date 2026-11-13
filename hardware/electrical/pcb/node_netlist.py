"""PlantPulse Node carrier board (PP-E-001) - design source of truth.

The netlist, footprints, placement and BOM data live here as plain Python so that the schematic
(.kicad_sch), the PCB (.kicad_pcb), the BOM and the consistency checks are all generated from one
description. All parts are through-hole so the board can be hand-assembled.

Coordinates: mm, board origin at the top-left board corner, y downwards (KiCad convention).
"""
from __future__ import annotations

from dataclasses import dataclass, field

BOARD_W, BOARD_H = 175.0, 120.0
ORIGIN = (30.0, 30.0)          # board corner on the KiCad sheet

FP = {
    "TB2": ("TerminalBlock_Phoenix", "TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal"),
    "TB4": ("TerminalBlock_Phoenix", "TerminalBlock_Phoenix_MKDS-1,5-4-5.08_1x04_P5.08mm_Horizontal"),
    "XH2": ("Connector_JST", "JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"),
    "XH3": ("Connector_JST", "JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical"),
    "XH4": ("Connector_JST", "JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical"),
    "FAN4": ("Connector", "FanPinHeader_1x04_P2.54mm_Vertical"),
    "S22": ("Connector_PinSocket_2.54mm", "PinSocket_1x22_P2.54mm_Vertical"),
    "S08": ("Connector_PinSocket_2.54mm", "PinSocket_1x08_P2.54mm_Vertical"),
    "H06": ("Connector_PinHeader_2.54mm", "PinHeader_1x06_P2.54mm_Vertical"),
    "TO220": ("Package_TO_SOT_THT", "TO-220-3_Vertical"),
    "TO92": ("Package_TO_SOT_THT", "TO-92_Inline_Wide"),
    "DIP20": ("Package_DIP", "DIP-20_W7.62mm"),
    "DIP28": ("Package_DIP", "DIP-28_W7.62mm"),
    "R": ("Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"),
    "C": ("Capacitor_THT", "C_Disc_D5.0mm_W2.5mm_P5.00mm"),
    "CP8": ("Capacitor_THT", "CP_Radial_D8.0mm_P3.50mm"),
    "CP10": ("Capacitor_THT", "CP_Radial_D10.0mm_P5.00mm"),
    "DO41": ("Diode_THT", "D_DO-41_SOD81_P10.16mm_Horizontal"),
    "DO15": ("Diode_THT", "D_DO-15_P12.70mm_Horizontal"),
    "TSR": ("Converter_DCDC", "Converter_DCDC_TRACO_TSR-1_THT"),
    "FUSE": ("Fuse", "Fuseholder_Cylinder-5x20mm_Schurter_0031_8201_Horizontal_Open"),
    "HOLE": ("MountingHole", "MountingHole_3.2mm_M3"),
}

SYM = {
    "TB2": "Connector_Generic:Conn_01x02", "TB4": "Connector_Generic:Conn_01x04",
    "XH2": "Connector_Generic:Conn_01x02", "XH3": "Connector_Generic:Conn_01x03", "XH4": "Connector_Generic:Conn_01x04",
    "FAN4": "Connector_Generic:Conn_01x04", "S22": "Connector_Generic:Conn_01x22", "S08": "Connector_Generic:Conn_01x08",
    "H06": "Connector_Generic:Conn_01x06", "TO220": "Transistor_FET:IRLB8721PBF", "TO92": "Transistor_FET:2N7000",
    "DIP20": "74xx:74HCT541", "DIP28": "Interface_Expansion:MCP23017_SP", "R": "Device:R", "C": "Device:C",
    "CP8": "Device:C_Polarized", "CP10": "Device:C_Polarized", "DO41": "Device:D_Schottky", "DO15": "Device:D_TVS",
    "TSR": "Regulator_Switching:TSR_1-2450", "FUSE": "Device:Fuse",
}

# net -> routing width (mm). Anything not listed uses SIGNAL_W.
SIGNAL_W = 0.3
NET_WIDTH = {
    "GND": 0.6,
    "+24V_ACT": 2.5, "HEATER_SW": 2.5, "+24V_LOGIC_IN": 0.8, "+24V_LOGIC_F": 0.8, "+24V_L": 0.8,
    "+12V": 1.0, "+5V": 0.8, "+5V_CAM": 0.8, "+3V3": 0.6, "PUMP_SW": 0.8, "PERI_SW": 0.8, "HUM_SW": 0.8,
    "IMG_SW": 0.8, "M_A1": 0.8, "M_A2": 0.8, "M_B1": 0.8, "M_B2": 0.8,
}
CLEARANCE = 0.2


@dataclass
class Part:
    ref: str
    value: str
    kind: str
    x: float
    y: float
    rot: float
    pins: dict            # pad number (str) -> net name ("" = no connect)
    mpn: str = ""
    desc: str = ""
    dnp: bool = False
    sheet: str = "io"


PARTS: list[Part] = []


def P(ref, value, kind, x, y, rot, pins, mpn="", desc="", sheet="io"):
    PARTS.append(Part(ref, value, kind, x, y, rot, {str(k): v for k, v in pins.items()}, mpn, desc, sheet=sheet))


# ---------------------------------------------------------------- power entry and regulation
P("J1", "PWR_IN", "TB4", 8, 14, 270, {1: "GND", 2: "+24V_LOGIC_IN", 3: "+24V_ACT", 4: "GND"}, "1715747", "Power input: GND / 24V logic / 24V actuators / GND", "power")
P("F1", "1A T", "FUSE", 22, 8, 0, {1: "+24V_LOGIC_IN", 2: "+24V_LOGIC_F"}, "0031.8201", "5x20 fuse holder + 1 A slow fuse (logic feed)", "power")
P("D1", "1N5819", "DO41", 22, 20, 0, {1: "+24V_L", 2: "+24V_LOGIC_F"}, "1N5819", "Reverse-polarity Schottky, logic feed", "power")
P("D2", "P6KE27A", "DO15", 22, 27, 0, {1: "+24V_L", 2: "GND"}, "P6KE27A", "TVS, logic feed", "power")
P("D3", "P6KE27A", "DO15", 22, 34, 0, {1: "+24V_ACT", 2: "GND"}, "P6KE27A", "TVS, actuator feed", "power")
P("C1", "100u/50V", "CP8", 40, 18, 0, {1: "+24V_L", 2: "GND"}, "", "Bulk, logic feed", "power")
P("C2", "470u/35V", "CP10", 12, 44, 0, {1: "+24V_ACT", 2: "GND"}, "", "Bulk, actuator feed", "power")
P("U1", "TSR 1-2450", "TSR", 48, 8, 0, {1: "+24V_L", 2: "GND", 3: "+5V"}, "TSR 1-2450", "5 V 1 A switching regulator (logic)", "power")
P("U2", "TSR 1-2450", "TSR", 48, 20, 0, {1: "+24V_L", 2: "GND", 3: "+5V_CAM"}, "TSR 1-2450", "5 V 1 A switching regulator (camera node)", "power")
P("U3", "TSR 2-24120", "TSR", 30, 44, 0, {1: "+24V_ACT", 2: "GND", 3: "+12V"}, "TSR 2-24120", "12 V 2 A switching regulator (fans, pumps, imaging LED)", "power")
P("C3", "22u/25V", "CP8", 62, 8, 0, {1: "+5V", 2: "GND"}, "", "", "power")
P("C4", "22u/25V", "CP8", 62, 20, 0, {1: "+5V_CAM", 2: "GND"}, "", "", "power")
P("C5", "100u/25V", "CP8", 44, 44, 0, {1: "+12V", 2: "GND"}, "", "", "power")
P("R1", "100k", "R", 10, 56, 0, {1: "+24V_ACT", 2: "ESTOP_OK"}, "", "E-stop sense divider (24 V present)", "power")
P("R2", "12k", "R", 10, 61, 0, {1: "ESTOP_OK", 2: "GND"}, "", "", "power")

# ---------------------------------------------------------------- MCU socket (ESP32-S3-DevKitC-1)
LEFT = ["+3V3", "+3V3", "", "OW", "LED_PWM", "IMG_LED", "CAM_TRIG", "CAM_BUSY", "HEATER", "PUMP", "PERI", "SDA",
        "", "", "SCL", "FAN1_PWM", "FAN2_PWM", "FAN3_PWM", "TACH1", "TACH2", "+5V", "GND"]
RIGHT = ["GND", "", "", "FLOW", "EXP_INT", "STEP_EN_N", "DIR", "STEP", "OUT_EN_N", "", "", "", "", "", "", "",
         "ENDSTOP", "HUMID", "", "", "GND", "GND"]
GPIO_LEFT = ["3V3", "3V3", "RST", "IO4", "IO5", "IO6", "IO7", "IO15", "IO16", "IO17", "IO18", "IO8", "IO3", "IO46",
             "IO9", "IO10", "IO11", "IO12", "IO13", "IO14", "5V", "GND"]
GPIO_RIGHT = ["GND", "TX", "RX", "IO1", "IO2", "IO42", "IO41", "IO40", "IO39", "IO38", "IO37", "IO36", "IO35", "IO0",
              "IO45", "IO48", "IO47", "IO21", "IO20", "IO19", "GND", "GND"]
P("J20", "ESP32-S3 L", "S22", 84, 22, 0, {i + 1: n for i, n in enumerate(LEFT)}, "ESP32-S3-DevKitC-1-N8R2", "DevKitC-1 left header socket", "mcu")
P("J21", "ESP32-S3 R (22.86)", "S22", 106.86, 22, 0, {i + 1: n for i, n in enumerate(RIGHT)}, "", "DevKitC-1 right header socket, 22.86 mm row spacing", "mcu")
P("J22", "ESP32-S3 R (25.40)", "S22", 109.40, 22, 0, {i + 1: n for i, n in enumerate(RIGHT)}, "", "Alternative right socket position, 25.4 mm row spacing (fit one)", "mcu")
P("C6", "100n", "C", 90, 16, 0, {1: "+3V3", 2: "GND"}, "", "", "mcu")
P("R3", "2k2", "R", 66, 60, 0, {1: "+3V3", 2: "SDA"}, "", "I2C pull-up", "mcu")
P("R4", "2k2", "R", 66, 64, 0, {1: "+3V3", 2: "SCL"}, "", "I2C pull-up", "mcu")
P("R5", "4k7", "R", 66, 30, 0, {1: "+3V3", 2: "OW"}, "", "1-Wire pull-up", "mcu")

# ---------------------------------------------------------------- output buffer (fail-safe enable) and MOSFETs
P("U4", "74HCT541", "DIP20", 122, 20, 0, {
    1: "OUT_EN_N", 2: "HEATER", 3: "PUMP", 4: "PERI", 5: "HUMID", 6: "IMG_LED", 7: "LED_PWM", 8: "GND", 9: "GND",
    10: "GND", 11: "", 12: "", 13: "LED_PWM_5V", 14: "IMG_G5", 15: "HUM_G5", 16: "PERI_G5", 17: "PUMP_G5",
    18: "HEAT_G5", 19: "OUT_EN_N", 20: "+5V"}, "SN74HCT541N", "3.3 V -> 5 V gate buffer; outputs hi-Z until OUT_EN_N is driven low", "outputs")
P("C7", "100n", "C", 126, 12, 0, {1: "+5V", 2: "GND"}, "", "", "outputs")
P("R6", "10k", "R", 112, 12, 0, {1: "+5V", 2: "OUT_EN_N"}, "", "Output-enable pull-up (outputs off by default)", "outputs")
outs = [("Q1", "HEAT", "HEATER_SW", 26), ("Q2", "PUMP", "PUMP_SW", 44), ("Q3", "PERI", "PERI_SW", 60),
        ("Q4", "HUM", "HUM_SW", 76), ("Q5", "IMG", "IMG_SW", 92)]
for k, (q, nm, sw, y) in enumerate(outs):
    P(q, "IRLB8721", "TO220", 152, y, 90, {1: f"{nm}_G", 2: sw, 3: "GND"}, "IRLB8721PBF", f"Low-side switch: {nm}", "outputs")
    P(f"R{10 + 2 * k}", "100R", "R", 136, y - 3, 0, {1: f"{nm}_G5", 2: f"{nm}_G"}, "", "Gate resistor", "outputs")
    P(f"R{11 + 2 * k}", "10k", "R", 136, y + 2, 0, {1: f"{nm}_G", 2: "GND"}, "", "Gate pull-down", "outputs")
P("J2", "HEATER", "TB2", 166, 24, 90, {1: "+24V_ACT", 2: "HEATER_SW"}, "1715721", "PTC heater (via external 45 C thermostat)", "outputs")
P("J3", "PUMP", "XH2", 167, 44, 90, {1: "+12V", 2: "PUMP_SW"}, "B2B-XH-A", "Circulation pump", "outputs")
P("J4", "PERI", "XH2", 167, 60, 90, {1: "+12V", 2: "PERI_SW"}, "B2B-XH-A", "Peristaltic top-up pump", "outputs")
P("J5", "HUMID", "XH2", 167, 76, 90, {1: "+5V", 2: "HUM_SW"}, "B2B-XH-A", "Ultrasonic humidifier module", "outputs")
P("J6", "IMG_LED", "XH2", 167, 92, 90, {1: "+12V", 2: "IMG_SW"}, "B2B-XH-A", "Imaging LED ring", "outputs")
P("D4", "1N5819", "DO41", 152, 51, 0, {1: "+12V", 2: "PUMP_SW"}, "1N5819", "Flyback, pump", "outputs")
P("D5", "1N5819", "DO41", 152, 67, 0, {1: "+12V", 2: "PERI_SW"}, "1N5819", "Flyback, peristaltic", "outputs")
P("R7", "10k", "R", 136, 8, 0, {1: "LED_PWM_5V", 2: "GND"}, "", "Holds LED drivers off while the buffer is disabled", "outputs")
P("J7", "LED_DIM", "XH3", 150, 8, 0, {1: "LED_PWM_5V", 2: "GND", 3: "GND"}, "B3B-XH-A", "PWM to LED constant-current drivers", "outputs")

# ---------------------------------------------------------------- fans
for i, x in enumerate((72, 88, 104)):
    n = i + 1
    P(f"J{10 + i}", f"FAN{n}", "FAN4", x, 6, 0, {1: "GND", 2: "+12V", 3: f"TACH{n}" if n < 3 else "", 4: f"FAN{n}_OD"}, "47053-1000", f"4-pin PWM fan {n}", "fans")
    P(f"Q{10 + i}", "2N7000", "TO92", x + 1.5, 13, 0, {1: "GND", 2: f"FAN{n}_PWM", 3: f"FAN{n}_OD"}, "2N7000", "Open-drain fan PWM (inverting)", "fans")
P("R30", "10k", "R", 66, 36, 0, {1: "+3V3", 2: "TACH1"}, "", "Tach pull-up", "fans")
P("R31", "10k", "R", 66, 40, 0, {1: "+3V3", 2: "TACH2"}, "", "Tach pull-up", "fans")

# ---------------------------------------------------------------- stepper driver (TMC2209 SilentStepStick pinout)
P("J30", "TMC2209 A", "S08", 30, 62, 0, {1: "STEP_EN_N", 2: "+3V3", 3: "+3V3", 4: "", 5: "", 6: "GND", 7: "STEP", 8: "DIR"}, "TMC2209 SilentStepStick", "Stepper driver socket, logic side (MS1 = MS2 = high: 1/16)", "motion")
P("J31", "TMC2209 B", "S08", 42.7, 62, 0, {1: "+24V_ACT", 2: "GND", 3: "M_B2", 4: "M_B1", 5: "M_A1", 6: "M_A2", 7: "+3V3", 8: "GND"}, "", "Stepper driver socket, motor side", "motion")
P("C8", "100u/35V", "CP8", 50, 60, 0, {1: "+24V_ACT", 2: "GND"}, "", "Stepper VMOT bulk", "motion")
P("J32", "MOTOR", "XH4", 48, 72, 90, {1: "M_B2", 2: "M_B1", 3: "M_A1", 4: "M_A2"}, "B4B-XH-A", "NEMA17 gantry motor", "motion")
P("J33", "ENDSTOP", "XH3", 48, 86, 90, {1: "+3V3", 2: "GND", 3: "ENDSTOP"}, "B3B-XH-A", "Gantry home switch", "motion")
P("R32", "10k", "R", 56, 96, 0, {1: "+3V3", 2: "ENDSTOP"}, "", "", "motion")

# ---------------------------------------------------------------- sensors
I2C_NAMES = ["SHT45", "SCD30", "AS7341", "NAU7802", "EZO_PH", "EZO_EC", "INA228_A", "INA228_B"]
for i, nm in enumerate(I2C_NAMES):
    P(f"J{40 + i}", nm, "XH4", 12 + i * 14.5, 112, 0, {1: "+3V3", 2: "GND", 3: "SDA", 4: "SCL"}, "B4B-XH-A", f"I2C: {nm}", "sensors")
P("J50", "DS18B20_A", "XH3", 130, 112, 0, {1: "+3V3", 2: "GND", 3: "OW"}, "B3B-XH-A", "1-Wire: solution temperature", "sensors")
P("J51", "DS18B20_B", "XH3", 142, 112, 0, {1: "+3V3", 2: "GND", 3: "OW"}, "B3B-XH-A", "1-Wire: heater outlet / spare", "sensors")
P("J52", "FLOW", "XH3", 156, 112, 0, {1: "+5V", 2: "GND", 3: "FLOW_5V"}, "B3B-XH-A", "Hall flow meter", "sensors")
P("R33", "10k", "R", 150, 103, 0, {1: "FLOW_5V", 2: "FLOW"}, "", "Flow divider (5 V -> 3.3 V)", "sensors")
P("R34", "20k", "R", 136, 103, 0, {1: "FLOW", 2: "GND"}, "", "", "sensors")
P("J53", "CAMERA", "XH4", 60, 86, 90, {1: "+5V_CAM", 2: "GND", 3: "CAM_TRIG", 4: "CAM_BUSY"}, "B4B-XH-A", "Camera node (Pi Zero 2 W): power, trigger, busy", "sensors")

# ---------------------------------------------------------------- I/O expander and digital inputs
P("U5", "MCP23017", "DIP28", 14, 70, 0, {
    1: "GPB0", 2: "GPB1", 3: "GPB2", 4: "GPB3", 5: "", 6: "", 7: "", 8: "", 9: "+3V3", 10: "GND", 11: "", 12: "SCL",
    13: "SDA", 14: "", 15: "GND", 16: "GND", 17: "GND", 18: "+3V3", 19: "", 20: "EXP_INT", 21: "FLOAT_LO",
    22: "FLOAT_HI", 23: "LEAK", 24: "DOOR", 25: "ESTOP_OK", 26: "", 27: "", 28: ""}, "MCP23017-E/SP", "I2C I/O expander (0x20): slow digital inputs", "inputs")
P("C9", "100n", "C", 6, 96, 0, {1: "+3V3", 2: "GND"}, "", "", "inputs")
for i, nm in enumerate(["FLOAT_LO", "FLOAT_HI", "LEAK", "DOOR"]):
    P(f"J{60 + i}", nm, "XH2", 74 + i * 10, 96, 0, {1: nm, 2: "GND"}, "B2B-XH-A", f"Switch input: {nm}", "inputs")
    P(f"R{40 + i}", "10k", "R", 74 + i * 10, 86, 90, {1: "+3V3", 2: nm}, "", "Input pull-up", "inputs")
P("J64", "EXP", "H06", 120, 84, 0, {1: "+3V3", 2: "GND", 3: "GPB0", 4: "GPB1", 5: "GPB2", 6: "GPB3"}, "", "Spare expander I/O", "inputs")

# ---------------------------------------------------------------- placement after DRC iteration
# The first placement produced courtyard overlaps; these positions supersede the values above.
# Pull-up resistors sit underneath the socketed DevKitC-1 (8.5 mm socket height clears axial parts).
PLACEMENT = {
    "U1": (54, 8, 0), "U2": (54, 20, 0), "C3": (67, 10, 0), "C4": (67, 21, 0), "C1": (42, 30, 0),
    "J10": (78, 6, 0), "J11": (93, 6, 0), "J12": (108, 6, 0), "Q10": (79.5, 16, 0), "Q11": (94.5, 16, 0), "Q12": (109.5, 16, 0),
    "J20": (83.82, 27.94, 0), "J21": (106.68, 27.94, 0), "J22": (109.22, 27.94, 0),
    "R3": (89, 34, 0), "R4": (89, 40, 0), "R5": (89, 46, 0), "R30": (89, 52, 0), "R31": (89, 58, 0), "R32": (89, 64, 0),
    "R40": (81.28, 98, 90), "R41": (93.98, 98, 90), "R42": (106.68, 98, 90), "R43": (119.38, 98, 90), "C6": (92, 72, 0),
    "R6": (136, 13, 0), "R7": (136, 8, 0), "J7": (156, 8, 0), "C7": (124, 15, 0),
    "D4": (136, 52, 0), "D5": (136, 68, 0),
    "C8": (54, 56, 0), "J32": (52, 80, 90), "J33": (52, 100, 90), "J53": (64, 94, 90),
    "J60": (73.66, 100, 0), "J61": (86.36, 100, 0), "J62": (99.06, 100, 0), "J63": (111.76, 100, 0),
    "J64": (128, 80, 0), "R33": (150, 105, 0), "R34": (134, 105, 0), "C9": (5, 106, 90),
}
for _p in PARTS:
    if _p.ref in PLACEMENT:
        _p.x, _p.y, _p.rot = PLACEMENT[_p.ref]

MOUNT_HOLES = [(4, 4), (BOARD_W - 4, 4), (4, BOARD_H - 4), (BOARD_W - 4, BOARD_H - 4)]

GPIO_MAP = {n: g for n, g in list(zip(LEFT, GPIO_LEFT)) + list(zip(RIGHT, GPIO_RIGHT)) if n and not n.startswith(("+", "GND"))}


def nets() -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
    for p in PARTS:
        for pad, net in p.pins.items():
            if net:
                out.setdefault(net, []).append((p.ref, pad))
    return out


def check() -> list[str]:
    """Static sanity checks on the netlist."""
    problems = []
    refs = [p.ref for p in PARTS]
    problems += [f"duplicate reference {r}" for r in set(refs) if refs.count(r) > 1]
    for net, pins in nets().items():
        if len(pins) < 2:
            problems.append(f"net {net} has a single pin {pins}")
    return problems


if __name__ == "__main__":
    print(len(PARTS), "parts,", len(nets()), "nets")
    print("problems:", check())
    for k, v in sorted(GPIO_MAP.items()):
        print(f"{v:5s} {k}")
