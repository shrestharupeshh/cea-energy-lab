"""PLANTPULSE LAB parametric CAD (CadQuery / OpenCASCADE).

All dimensions come from hardware/design_parameters.yaml. Coordinates of a pod: origin at the
outer front-left-bottom corner of the frame, x = width, y = depth (front to back), z = up.

Usage:  python hardware/mechanical/cad/build_all.py
The STEP output opens directly in SolidWorks, FreeCAD, Fusion and Onshape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cadquery as cq
import yaml

ROOT = Path(__file__).resolve().parents[3]
P = yaml.safe_load((ROOT / "hardware" / "design_parameters.yaml").read_text())

E = P["pod"]["extrusion"]                       # 20
CW, CD = P["pod"]["chamber_w"], P["pod"]["chamber_d"]
SB = P["pod"]["service_bay_w"]
MH = P["pod"]["module_h"]
PT = P["pod"]["panel_t"]
POD_W = E + CW + E + (SB - E) + E               # 1040
POD_D = CD + 2 * E                              # 540
Z_FLOOR = E + P["pod"]["base_panel_t"]          # 25  top of floor panel
Z_LID = Z_FLOOR + P["tub"]["ext_h"] + P["tub"]["lid_t"]   # 201 top of lid
Z_MID = Z_LID + P["pod"]["canopy_clear_h"]      # 740 underside of mid ring
Z_WIN = Z_MID + E                               # 760 underside of window
Z_TOP = MH - E                                  # 860 underside of top ring
TUB_X = E + P["tub"]["tub_offset_x"]            # 120
TUB_Y = E + P["tub"]["tub_offset_y"]            # 70
Z_LENS = Z_LID + P["imaging"]["lens_to_lid"]    # 701 lens front
Z_BEAM = 715.0                                  # underside of gantry beam / arm

COL = {
    "al": cq.Color(0.75, 0.77, 0.80), "pvc": cq.Color(0.96, 0.96, 0.94, 1.0), "black": cq.Color(0.08, 0.08, 0.08),
    "tub": cq.Color(0.25, 0.3, 0.38), "acrylic": cq.Color(0.7, 0.9, 1.0, 0.3), "led": cq.Color(1.0, 0.92, 0.6),
    "print": cq.Color(0.95, 0.45, 0.1), "steel": cq.Color(0.45, 0.45, 0.5), "pcb": cq.Color(0.1, 0.45, 0.2),
    "fan": cq.Color(0.55, 0.42, 0.3), "grey": cq.Color(0.6, 0.6, 0.62), "water": cq.Color(0.3, 0.55, 0.9, 0.5),
    "green": cq.Color(0.3, 0.7, 0.25),
}


def box(dx, dy, dz, x0=0.0, y0=0.0, z0=0.0):
    return cq.Workplane("XY").box(dx, dy, dz, centered=False).translate((x0, y0, z0))


# ----------------------------------------------------------------------------- stock parts
def _profile_2020():
    s = 20.0
    w = cq.Workplane("XY").rect(s, s).extrude(1)
    slot = cq.Workplane("XY").rect(6.2, 6.0).extrude(1)
    for ang in (0, 90, 180, 270):
        w = w.cut(slot.translate((0, s / 2 - 3.0, 0)).rotate((0, 0, 0), (0, 0, 1), ang))
    return w.cut(cq.Workplane("XY").circle(2.1).extrude(1))


_EXTR_CACHE: dict = {}


def extrusion(length: float, axis: str):
    """2020 T-slot profile of given length along axis, min corner at the origin."""
    key = (round(length, 2), axis)
    if key not in _EXTR_CACHE:
        s = 20.0
        w = cq.Workplane("XY").rect(s, s).extrude(length)
        slot = cq.Workplane("XY").rect(6.2, 6.0).extrude(length)
        for ang in (0, 90, 180, 270):
            w = w.cut(slot.translate((0, s / 2 - 3.0, 0)).rotate((0, 0, 0), (0, 0, 1), ang))
        w = w.cut(cq.Workplane("XY").circle(2.1).extrude(length))
        if axis == "x":
            w = w.rotate((0, 0, 0), (0, 1, 0), 90).translate((0, 10, 10))
        elif axis == "y":
            w = w.rotate((0, 0, 0), (1, 0, 0), -90).translate((10, 0, 10))
        else:
            w = w.translate((10, 10, 0))
        _EXTR_CACHE[key] = w
    return _EXTR_CACHE[key]


def tub():
    t = P["tub"]
    outer = box(t["ext_l"], t["ext_w"], t["ext_h"]).edges("|Z").fillet(12)
    body = outer.faces(">Z").shell(-t["wall_t"])
    rim = (box(t["ext_l"], t["ext_w"], 12, 0, 0, t["ext_h"] - 12).edges("|Z").fillet(12)
           .cut(box(t["ext_l"] - 16, t["ext_w"] - 16, 12, 8, 8, t["ext_h"] - 12)))
    return body.union(rim)


def lid():
    """Tub lid / raft: 6 net-pot holes plus probe, tube and fiducial features (laser/CNC cut)."""
    t = P["tub"]
    w = box(t["ext_l"], t["ext_w"], t["lid_t"])
    pts = [(x, y) for x in t["plant_cols_x"] for y in t["plant_rows_y"]]
    w = w.faces(">Z").workplane(origin=(0, 0, 0)).pushPoints(pts).hole(t["net_pot_hole_d"])
    probe_pts = [(575, 120), (575, 200), (575, 280)]       # pH, EC, temperature
    w = w.faces(">Z").workplane(origin=(0, 0, 0)).pushPoints(probe_pts).hole(16.0)
    tube_pts = [(25, 150), (25, 250), (25, 200)]           # pump suction, return, air line
    w = w.faces(">Z").workplane(origin=(0, 0, 0)).pushPoints(tube_pts).hole(12.5)
    w = w.faces(">Z").workplane(origin=(0, 0, 0)).pushPoints([(575, 350), (575, 50)]).hole(22.0)  # float switch, top-up
    return w


def net_pot():
    outer = cq.Workplane("XY").circle(19).workplane(offset=50).circle(25.4).loft(combine=True)
    inner = cq.Workplane("XY").workplane(offset=1.2).circle(17.8).workplane(offset=48.8).circle(24.2).loft(combine=True)
    rim = cq.Workplane("XY").workplane(offset=50).circle(31).circle(24.2).extrude(2)
    return outer.cut(inner).union(rim)


def lettuce_placeholder(d=180.0, h=110.0):
    return cq.Workplane("XY").sphere(d / 2).translate((0, 0, 0)).intersect(box(d, d, h, -d / 2, -d / 2, 0)) \
        .union(cq.Workplane("XY").circle(12).extrude(-40))


def window():
    w = box(CW + 2 * E - 2, POD_D - 2, P["pod"]["window_t"], 1, 1, 0)
    for (x, y) in [(0, 0), (CW + E - 1, 0), (0, POD_D - E - 1), (CW + E - 1, POD_D - E - 1)]:
        w = w.cut(box(E + 1, E + 1, 10, x, y, -1))
    return w


def led_strip():
    lt = P["lighting"]
    pcb = box(lt["strip_len"], lt["strip_w"], 1.6, -lt["strip_len"] / 2, -lt["strip_w"] / 2, 0.7)
    leds = box(lt["strip_len"] - 20, 6, 0.7, -lt["strip_len"] / 2 + 10, -3, 0)
    return pcb.union(leds)


def fan80():
    b = box(80, 80, 25).edges("|Z").fillet(4)
    b = b.faces(">Z").workplane().hole(76)
    b = b.faces(">Z").workplane().rect(71.5, 71.5, forConstruction=True).vertices().hole(4.3)
    hub = cq.Workplane("XY").circle(18).extrude(25).translate((40, 40, 0))
    return b.union(hub)


def nema17():
    body = box(42.3, 42.3, 40).edges("|Z").chamfer(4)
    boss = cq.Workplane("XY").circle(11).extrude(2).translate((21.15, 21.15, 40))
    shaft = cq.Workplane("XY").circle(2.5).extrude(24).translate((21.15, 21.15, 40))
    pulley = cq.Workplane("XY").circle(6.4).extrude(14).translate((21.15, 21.15, 48))
    return body.union(boss).union(shaft).union(pulley)


def mgn12_rail(length):
    return box(length, 8, 12).faces(">Y").workplane().rarray(25, 1, int(length // 25), 1).hole(3.5, 4)


def mgn12h_block():
    return box(45.4, 13, 27).cut(box(45.4, 5, 12.4, 0, 0, 7.3))


def hq_camera():
    """Raspberry Pi HQ camera (38 x 38 mm board, CS mount) with 6 mm lens, optical axis along -Z,
    origin at the lens front centre."""
    lens = cq.Workplane("XY").circle(15).extrude(28)
    mount = cq.Workplane("XY").circle(17.5).extrude(11).translate((0, 0, 28))
    board = box(38, 38, 1.6, -19, -19, 39).faces(">Z").workplane().rect(30, 30, forConstruction=True).vertices().hole(2.7)
    return lens.union(mount).union(board)


def pi_zero():
    return box(65, 30, 1.6).faces(">Z").workplane().rect(58, 23, forConstruction=True).vertices().hole(2.7) \
        .union(box(12, 12, 3, 26, 9, 1.6))


def jerrycan():
    b = box(135, 190, 240).edges("|Z").fillet(15).edges(">Z").fillet(8)
    neck = cq.Workplane("XY").circle(20).extrude(15).translate((67.5, 40, 240))
    return b.union(neck)


def enclosure(w=120, d=75, h=200):
    return box(w, d, h).edges("|Y").fillet(6)


def foot():
    return cq.Workplane("XY").circle(20).extrude(12).union(cq.Workplane("XY").circle(4).extrude(100))


# ----------------------------------------------------------------------------- printed / fabricated parts
def carriage_plate():
    """Aluminium or PETG plate on the MGN12H block; carries the 2020 arm and clamps the GT2 belt."""
    w = box(60, 6, 60)
    w = w.faces("<Y").workplane(origin=(30, 0, 30)).rect(20, 20, forConstruction=True).vertices().cboreHole(3.4, 6.2, 3.2)
    w = w.faces("<Y").workplane(origin=(30, 0, 30)).pushPoints([(-20, 20), (20, 20)]).hole(5.3)   # arm bracket M5
    clamp = box(24, 10, 8, 18, -10, 52).cut(box(24, 1.8, 6.5, 18, -6, 52))                        # belt slot
    return w.union(clamp)


def camera_mount():
    """Printed bracket: bolts to the end of the 2020 arm (M5), holds HQ camera (30 mm M2.5 pattern),
    Pi Zero 2 W (58 x 23 mm M2.5 pattern) and the imaging LED ring. Origin at optical axis, z = board plane."""
    base = box(46, 46, 4, -23, -23, 0)
    base = base.faces(">Z").workplane(origin=(0, 0, 0)).rect(30, 30, forConstruction=True).vertices().hole(2.8)
    base = base.faces(">Z").workplane(origin=(0, 0, 0)).hole(36.0)                    # CS-mount ring clearance
    tab = box(20, 30, 4, -10, 23, 0).faces(">Z").workplane(origin=(0, 38, 0)).pushPoints([(0, -6), (0, 8)]).hole(5.3)
    pi = box(70, 4, 34, -35, -27, -30)                                   # hangs below the board plane (window clearance)
    pi = pi.faces("<Y").workplane(origin=(0, 0, -13)).rect(58, 23, forConstruction=True).vertices().hole(2.8)
    ring = (cq.Workplane("XY").circle(48).circle(40).extrude(3).translate((0, 0, -42)))  # LED ring seat
    legs = None
    for ang in (45, 135, 225, 315):
        import math
        x, y = 44 * math.cos(math.radians(ang)), 44 * math.sin(math.radians(ang))
        leg = cq.Workplane("XY").circle(2.5).extrude(42).translate((x * 0.5 + 0, y * 0.5, -42))
        legs = leg if legs is None else legs.union(leg)
    arms = None
    for ang in (45, 135, 225, 315):
        import math
        x, y = 22 * math.cos(math.radians(ang)), 22 * math.sin(math.radians(ang))
        a = box(24, 5, 3, -2, -2.5, -42).rotate((0, 0, 0), (0, 0, 1), ang).translate((x, y, 0))
        arms = a if arms is None else arms.union(a)
    return base.union(tab).union(pi).union(ring).union(legs).union(arms)


def motor_mount():
    """NEMA17 bracket bolted to the top slot of the 2020 gantry beam; motor axis vertical."""
    plate = box(60, 46, 5)
    plate = plate.faces(">Z").workplane(origin=(34, 23, 5)).rect(31, 31, forConstruction=True).vertices().hole(3.4)
    plate = plate.faces(">Z").workplane(origin=(34, 23, 5)).hole(23)
    foot_ = box(60, 5, 25, 0, 46, -20).faces(">Y").workplane(origin=(30, 0, -10)).pushPoints([(-20, 0), (20, 0)]).hole(5.3)
    rib = box(5, 46, 20, 0, 0, -20).union(box(5, 46, 20, 55, 0, -20))
    return plate.union(foot_).union(rib)


def idler_mount():
    plate = box(40, 40, 5)
    plate = plate.faces(">Z").workplane(origin=(20, 18, 5)).hole(5.1)     # idler shaft M5
    foot_ = box(40, 5, 25, 0, 40, -20).faces(">Y").workplane(origin=(20, 0, -10)).pushPoints([(-12, 0), (12, 0)]).hole(5.3)
    return plate.union(foot_)


def endstop_mount():
    w = box(30, 5, 20).faces(">Y").workplane(origin=(15, 0, 10)).hole(5.3)
    tab = box(22, 16, 4, 4, -16, 0).faces(">Z").workplane(origin=(15, -8, 4)).pushPoints([(-4.75, 0), (4.75, 0)]).hole(2.2)
    return w.union(tab)


def light_trap():
    """Labyrinth light trap for an 80 mm fan port: two offset baffles, matte black print.
    Open area of each gap equals the fan duct area to keep the loss coefficient moderate."""
    outer = box(100, 100, 70)
    cavity = box(94, 94, 64, 3, 3, 3)
    w = outer.cut(cavity)
    w = w.faces("<Z").workplane(origin=(50, 50, 0)).hole(76)
    w = w.faces("<Z").workplane(origin=(50, 50, 0)).rect(71.5, 71.5, forConstruction=True).vertices().hole(4.3)
    w = w.cut(box(94, 30, 6, 3, 67, 64).translate((0, 0, 3)))            # outlet slot on the top face near +Y edge
    baffle1 = box(94, 62, 2.4, 3, 3, 24)
    baffle2 = box(94, 62, 2.4, 3, 35, 46)
    flange = box(120, 100, 3, -10, 0, 0).cut(box(100, 100, 3)).faces(">Z").workplane(origin=(50, 50, 3)) \
        .pushPoints([(-55, -35), (-55, 35), (55, -35), (55, 35)]).hole(4.3)
    return w.union(baffle1).union(baffle2).union(flange)


def sensor_shield():
    """Fan-aspirated radiation shield for SHT45 + SCD30: double-walled white tube, 30 mm fan at the top."""
    outer = cq.Workplane("XY").circle(30).circle(27.6).extrude(100)
    inner = cq.Workplane("XY").circle(22).circle(20).extrude(90).translate((0, 0, 5))
    spokes = None
    for ang in (0, 120, 240):
        s = box(8, 2, 90, 20, -1, 5).rotate((0, 0, 0), (0, 0, 1), ang)
        spokes = s if spokes is None else spokes.union(s)
    top = cq.Workplane("XY").rect(34, 34).circle(14).extrude(3).translate((0, 0, 100)) \
        .faces(">Z").workplane().rect(24, 24, forConstruction=True).vertices().hole(3.2)
    tray = box(28, 2, 60, -14, -19, 20)                                    # sensor PCB carrier
    bracket = box(40, 6, 30, -20, 28, 35).faces(">Y").workplane(origin=(0, 0, 50)).pushPoints([(-12, 0), (12, 0)]).hole(4.3)
    return outer.union(inner).union(spokes).union(top).union(tray).union(bracket)


def probe_adapter():
    """Lid port bushing for 12 mm pH/EC probes (push fit with O-ring groove)."""
    w = cq.Workplane("XY").circle(11).extrude(3).union(cq.Workplane("XY").circle(7.9).extrude(-8))
    return w.faces(">Z").workplane().hole(12.3)


def loadcell_cradle():
    """Platform for the 5 L top-up reservoir on a single bar load cell (80 x 12.7 x 12.7, M4/M5 holes)."""
    plate = box(140, 195, 4).edges("|Z").fillet(6)
    lip = box(140, 195, 12).edges("|Z").fillet(6).cut(box(134, 189, 12, 3, 3, 0)).translate((0, 0, 4))
    boss = box(30, 40, 6, 55, 77.5, -6).faces("<Z").workplane(origin=(70, 97.5, -6)).pushPoints([(0, -7.5), (0, 7.5)]).hole(4.3)
    return plate.union(lip).union(boss)


def float_bracket():
    w = box(40, 20, 4).faces(">Z").workplane(origin=(12, 10, 4)).hole(10.2)
    return w.union(box(4, 20, 30, 36, 0, -26)).faces(">X").workplane(origin=(40, 10, -14)).hole(4.3)


PRINTED = {
    "PP-M-101_carriage_plate": carriage_plate, "PP-M-102_camera_mount": camera_mount,
    "PP-M-103_motor_mount": motor_mount, "PP-M-104_idler_mount": idler_mount,
    "PP-M-105_endstop_mount": endstop_mount, "PP-M-106_light_trap": light_trap,
    "PP-M-107_sensor_shield": sensor_shield, "PP-M-108_probe_adapter": probe_adapter,
    "PP-M-109_loadcell_cradle": loadcell_cradle, "PP-M-110_float_bracket": float_bracket,
}


# ----------------------------------------------------------------------------- assembly
@dataclass
class Bom:
    rows: list = field(default_factory=list)

    def add(self, pn, desc, material, qty=1, length=None, category="fabricated"):
        for r in self.rows:
            if r["part_no"] == pn and r["length_mm"] == length:
                r["qty"] += qty
                return
        self.rows.append({"part_no": pn, "description": desc, "material": material, "qty": qty,
                          "length_mm": length, "category": category})


def build_pod(with_plants: bool = True, gantry_x: float | None = None):
    """Return (assembly, bom) for one pod. gantry_x = camera x in chamber coordinates (default: parked)."""
    a = cq.Assembly(name="pod")
    bom = Bom()
    n = [0]

    def add(shape, name, color, loc=(0, 0, 0)):
        n[0] += 1
        a.add(shape, name=f"{name}_{n[0]:03d}", color=COL[color], loc=cq.Location(cq.Vector(*loc)))

    def ext(length, axis, loc, role):
        add(extrusion(length, axis), f"ext2020_{role}", "al", loc)
        bom.add("PP-M-001", "2020 T-slot extrusion, 6063-T5, clear anodised", "Al 6063-T5", 1, length, "extrusion")

    col_x = [0, E + CW, POD_W - E]
    for x in col_x:
        for y in (0, POD_D - E):
            ext(MH, "z", (x, y, 0), "column")
    for z in (0, Z_MID, Z_TOP):
        for y in (0, POD_D - E):
            ext(CW, "x", (E, y, z), "rail_x")
            ext(SB - E, "x", (2 * E + CW, y, z), "rail_x_bay")
        for x in col_x:
            ext(CD, "y", (x, E, z), "rail_y")
    for x in (TUB_X + 100, TUB_X + 480):
        ext(CD, "y", (x, E, 0), "tub_support")
    ext(CW, "x", (E, POD_D - 2 * E, Z_BEAM), "gantry_beam")
    for y in (80, 230):                                         # reservoir shelf
        ext(SB - E, "x", (2 * E + CW, y, 280), "shelf")

    # panels (5 mm expanded PVC, slot mounted unless noted)
    def panel(dx, dy, dz, loc, pn, desc, color="pvc", material="Expanded PVC 5 mm, white"):
        add(box(dx, dy, dz), pn, color, loc)
        dims = sorted([dx, dy, dz])
        bom.add(pn, f"{desc} {dims[2]:.0f} x {dims[1]:.0f} x {dims[0]:.0f}", material, 1, None, "sheet")

    panel(CW, CD, P["pod"]["base_panel_t"], (E, E, E), "PP-M-010", "Floor panel")
    panel(CW + 10, PT, MH - 2 * E + 10, (E - 5, POD_D - 12.5, E - 5), "PP-M-011", "Back panel, chamber")
    panel(PT, CD + 10, MH - 2 * E + 10, (7.5, E - 5, E - 5), "PP-M-012", "Left side panel")
    panel(PT, CD + 10, MH - 2 * E + 10, (E + CW + 7.5, E - 5, E - 5), "PP-M-013", "Partition panel")
    panel(PT, CD + 10, MH - 2 * E + 10, (POD_W - 12.5, E - 5, E - 5), "PP-M-014", "Right side panel")
    panel(SB - E + 10, PT, MH - 2 * E + 10, (2 * E + CW - 5, POD_D - 12.5, E - 5), "PP-M-015", "Back panel, service bay")
    panel(POD_W, POD_D, PT, (0, 0, MH), "PP-M-016", "Top cover")
    panel(CW + 2 * E - 4, PT, Z_MID - E - 4 + E, (2, -PT, E + 2), "PP-M-017", "Chamber door (hinged, gasketed)")
    panel(CW + 2 * E - 4, PT, MH - Z_WIN - 4, (2, -PT, Z_WIN + 2), "PP-M-018", "LED bay front cover")
    panel(SB - 4, PT, MH - 4, (CW + 2 * E + 2, -PT, 2), "PP-M-019", "Service bay door")
    panel(SB - E, CD, PT, (2 * E + CW, E, E), "PP-M-020", "Service bay floor")

    add(window(), "PP-M-021_window", "acrylic", (0, 0, Z_WIN))
    bom.add("PP-M-021", "LED window, cast acrylic 3 mm, 838 x 538, corner notched", "PMMA cast, clear", 1, None, "sheet")

    # root zone
    t = P["tub"]
    add(tub(), "tub", "tub", (TUB_X, TUB_Y, Z_FLOOR))
    bom.add("PP-P-201", "Euro container 600 x 400 x 170, opaque PP", "PP", 1, None, "purchased")
    add(lid(), "PP-M-022_lid", "black", (TUB_X, TUB_Y, Z_FLOOR + t["ext_h"]))
    bom.add("PP-M-022", "Tub lid 600 x 400 x 6, 6 x 51 mm holes + ports", "Expanded PVC 6 mm, matte black", 1, None, "sheet")
    water = box(t["ext_l"] - 8, t["ext_w"] - 8, t["solution_depth"], 4, 4, 3)
    add(water, "solution", "water", (TUB_X, TUB_Y, Z_FLOOR))
    _pot, _plant = net_pot(), lettuce_placeholder()
    for px in t["plant_cols_x"]:
        for py in t["plant_rows_y"]:
            add(_pot, "net_pot", "black", (TUB_X + px, TUB_Y + py, Z_LID - 50))
            bom.add("PP-P-202", "Net pot 2 inch", "PP", 1, None, "purchased")
            if with_plants:
                add(_plant, "lettuce_envelope", "green", (TUB_X + px, TUB_Y + py, Z_LID + 2))
    for (px, py) in [(575, 120), (575, 200)]:
        add(probe_adapter(), "PP-M-108_probe_adapter", "print", (TUB_X + px, TUB_Y + py, Z_LID))
        add(cq.Workplane("XY").circle(6).extrude(150).translate((0, 0, -110)), "probe", "grey", (TUB_X + px, TUB_Y + py, Z_LID))

    # lighting
    lt = P["lighting"]
    add(box(CW - 20, CD - 20, 3), "PP-M-023_led_plate", "al", (E + 10, E + 10, Z_TOP - 3))
    bom.add("PP-M-023", "LED heat-spreader plate 780 x 480 x 3", "Al 5052-H32", 1, None, "sheet")
    _strip = led_strip()
    for y in lt["strip_y_positions"]:
        add(_strip, "led_strip", "led", (E + lt["strip_x_center"], E + y, Z_TOP - 3 - 2.3))
        bom.add("PP-P-301", f"LED strip {lt['strip_mpn']}", "-", 1, None, "purchased")

    # gantry
    im = P["imaging"]
    rail_y = POD_D - 2 * E - 8
    add(mgn12_rail(im["rail_len"]), "mgn12_rail", "steel", (E + 20, rail_y, Z_BEAM + 4))
    bom.add("PP-P-401", "Linear rail MGN12, 700 mm, with MGN12H carriage", "steel", 1, None, "purchased")
    gx = E + (im["park_x"] if gantry_x is None else gantry_x)
    add(mgn12h_block(), "mgn12h", "steel", (gx - 22.7, rail_y - 13, Z_BEAM - 3.5))
    add(carriage_plate(), "PP-M-101_carriage_plate", "print", (gx - 30, rail_y - 19, Z_BEAM - 20))
    arm_len = im["arm_len"]
    y_axis = E + CD / 2                                                 # optical axis y
    ext(arm_len - 30, "y", (gx - 10, rail_y - 19 - (arm_len - 30), Z_BEAM), "camera_arm")
    add(camera_mount(), "PP-M-102_camera_mount", "print", (gx, y_axis, Z_LENS + 39 - 4))
    add(hq_camera(), "hq_camera", "pcb", (gx, y_axis, Z_LENS))
    bom.add("PP-P-402", "Raspberry Pi HQ camera + 6 mm CS lens", "-", 1, None, "purchased")
    bom.add("PP-P-403", "Raspberry Pi Zero 2 W", "-", 1, None, "purchased")
    add(nema17(), "nema17", "black", (E + CW - 62, POD_D - 2 * E - 46, Z_BEAM - 62))
    add(motor_mount(), "PP-M-103_motor_mount", "print", (E + CW - 75, POD_D - 2 * E - 46, Z_BEAM - 22 + 0))
    add(idler_mount(), "PP-M-104_idler_mount", "print", (E + 2, POD_D - 2 * E - 40, Z_BEAM - 22))
    add(endstop_mount(), "PP-M-105_endstop_mount", "print", (E + 4, POD_D - 2 * E - 5, Z_BEAM + 22))
    bom.add("PP-P-404", "NEMA17 stepper 42 x 40 mm, 1.8 deg", "-", 1, None, "purchased")
    belt = box(CW - 100, 1.4, 6, E + 40, POD_D - 2 * E - 32, Z_BEAM - 12).union(box(CW - 100, 1.4, 6, E + 40, POD_D - 2 * E - 20, Z_BEAM - 12))
    add(belt, "gt2_belt", "black")
    bom.add("PP-P-405", "GT2 belt 6 mm, open, 1.7 m + 20T pulley + idler", "-", 1, None, "purchased")

    # air handling
    fan_v = fan80().rotate((0, 0, 0), (0, 1, 0), 90)                    # axis along x
    add(fan_v, "exhaust_fan", "fan", (E - 25 - 0, 230, 700))
    add(light_trap().rotate((0, 0, 0), (0, 1, 0), -90), "PP-M-106_light_trap_exhaust", "black", (0, 220, 600))
    fan_b = fan80().rotate((0, 0, 0), (1, 0, 0), -90)                   # axis along y
    add(light_trap().rotate((0, 0, 0), (1, 0, 0), -90), "PP-M-106_light_trap_inlet", "black", (E + CW - 130, POD_D, 330))
    add(fan_v, "mixing_fan", "fan", (E + CW - 30, 230, 420))
    add(fan_v, "led_bay_fan", "fan", (E - 25, 230, Z_WIN + 85))
    for _ in range(3):
        bom.add("PP-P-501", f"Fan 80 x 25 mm PWM {P['air']['fan_mpn']}", "-", 1, None, "purchased")
    add(sensor_shield(), "PP-M-107_sensor_shield", "pvc", (E + CW - 60, POD_D - E - 34 - 6, Z_LID + 120))
    heater = box(80, 60, 80)
    add(heater, "ptc_heater", "grey", (E + CW - 90, E + 10, Z_LID + 40))
    bom.add("PP-P-502", "PTC fan heater 24 V 100 W with 45 C cut-out", "-", 1, None, "purchased")

    # service bay
    bx = 2 * E + CW
    add(enclosure(), "node_enclosure", "grey", (bx + 30, POD_D - E - 75 - 8, 600))
    bom.add("PP-P-601", "IP65 ABS enclosure 200 x 120 x 75 (node electronics)", "ABS", 1, None, "purchased")
    add(loadcell_cradle(), "PP-M-109_loadcell_cradle", "print", (bx + 20, 60, 318))
    add(box(80, 12.7, 12.7), "load_cell", "al", (bx + 50, 151, 300))
    add(jerrycan(), "topup_reservoir", "pvc", (bx + 22.5, 62.5, 322))
    bom.add("PP-P-602", "Top-up reservoir 5 L HDPE", "HDPE", 1, None, "purchased")
    bom.add("PP-P-603", "Bar load cell 5 kg (TAL220B class)", "-", 1, None, "purchased")
    add(box(60, 45, 45), "circ_pump", "black", (bx + 30, 120, E + PT))
    add(cq.Workplane("YZ").circle(12).extrude(60), "flow_meter", "grey", (bx + 30, 230, E + PT + 20))
    add(box(60, 50, 60), "peristaltic_pump", "grey", (bx + 10, 300, 200))
    bom.add("PP-P-604", "Circulation pump 12 V brushless", "-", 1, None, "purchased")
    bom.add("PP-P-605", "Flow meter, hall, 0.3-6 L/min", "-", 1, None, "purchased")
    bom.add("PP-P-606", "Peristaltic pump 12 V", "-", 1, None, "purchased")
    for pn in ("PP-M-101", "PP-M-102", "PP-M-103", "PP-M-104", "PP-M-105", "PP-M-107", "PP-M-109", "PP-M-110"):
        bom.add(pn, [k for k in PRINTED if k.startswith(pn)][0].split("_", 1)[1].replace("_", " "), "PETG, printed", 1, None, "printed")
    bom.add("PP-M-106", "light trap", "PETG matte black, printed", 3, None, "printed")
    bom.add("PP-M-108", "probe adapter", "PETG, printed", 2, None, "printed")
    return a, bom


def build_rack():
    pod, bom = build_pod(with_plants=True)
    rack = cq.Assembly(name="plantpulse_rack")
    cols, tiers = P["facility"]["rack_layout"]
    k = 0
    for c in range(cols):
        for t in range(tiers):
            k += 1
            rack.add(pod, name=f"pod{k}", loc=cq.Location(cq.Vector(c * POD_W, 0, 100 + t * (MH + PT))))
    i = 0
    for x in (20, POD_W, 2 * POD_W - 20):
        for y in (20, POD_D - 20):
            i += 1
            rack.add(foot(), name=f"foot{i}", color=COL["steel"], loc=cq.Location(cq.Vector(x, y, 0)))
    rack.add(box(150, 300, 400), name="power_enclosure", color=COL["grey"],
             loc=cq.Location(cq.Vector(cols * POD_W + 5, 120, 700)))
    rack.add(box(120, 160, 60), name="central_computer", color=COL["pcb"],
             loc=cq.Location(cq.Vector(cols * POD_W + 5, 190, 1200)))
    return rack, bom
