"""Regenerate every mechanical output from the parametric model.

Outputs (hardware/mechanical/output/):
  step/   pod and rack assemblies, every printed part
  stl/, 3mf/   printed parts
  dxf/    sheet parts for laser / CNC cutting
  drawings/   SVG + PDF sheets (assembly views, part drawings with principal dimensions)
  bom_mechanical.csv, interference_report.txt
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import cadquery as cq
from cadquery import exporters

sys.path.insert(0, str(Path(__file__).parent))
import plantpulse_cad as m  # noqa: E402

OUT = m.ROOT / "hardware" / "mechanical" / "output"
SHEET_W, SHEET_H = 1189, 841  # A0 landscape units for assemblies; scaled into the page


def _oriented(shape, view):
    """Rotate the shape so that the requested orthographic view is seen from +Z with a sensible up vector
    (CadQuery's SVG exporter does not let the caller choose the up direction)."""
    if view == "FRONT":      # x right, z up
        return shape.rotate((0, 0, 0), (1, 0, 0), -90)
    if view == "RIGHT":      # y right, z up
        return shape.rotate((0, 0, 0), (0, 0, 1), -90).rotate((0, 0, 0), (1, 0, 0), -90)
    if view == "ISOMETRIC":  # from front-right-top
        return shape.rotate((0, 0, 0), (0, 0, 1), -45).rotate((0, 0, 0), (1, 0, 0), -54.74)
    return shape             # TOP: x right, y up


def _svg_view(shape, view, width=520, height=350, hidden=False):
    if isinstance(shape, cq.Workplane):
        shape = shape.val()
    shape = _oriented(shape, view)
    bb = shape.BoundingBox()
    svg = exporters.getSVG(shape, opts={
        "width": width, "height": height, "marginLeft": 10, "marginTop": 10, "showAxes": False,
        "projectionDir": (0, 0, 1), "strokeWidth": max(bb.DiagonalLength / 900, 0.05), "strokeColor": (0, 0, 0),
        "hiddenColor": (140, 140, 140), "showHidden": hidden,
    })
    return re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1)


def drawing_sheet(shape, title, number, dims: list[str], path: Path, scale_note="NTS", hidden=False):
    """Four-view sheet (front, top, right, isometric) with title block and principal dimensions."""
    views = [("FRONT", 20, 20), ("TOP", 20, 385), ("RIGHT", 560, 20), ("ISOMETRIC", 560, 385)]
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="860" viewBox="0 0 1120 860">',
             '<rect x="2" y="2" width="1116" height="856" fill="white" stroke="black" stroke-width="1.5"/>']
    for name, x, y in views:
        parts.append(f'<g transform="translate({x},{y})">{_svg_view(shape, name, hidden=hidden)}</g>')
        parts.append(f'<text x="{x + 8}" y="{y + 14}" font-family="monospace" font-size="11">{name}</text>')
    parts.append('<rect x="700" y="744" width="416" height="112" fill="white" stroke="black"/>')
    parts.append(f'<text x="708" y="764" font-family="sans-serif" font-size="13" font-weight="bold">{title[:56]}</text>')
    parts.append(f'<text x="708" y="784" font-family="monospace" font-size="11">DWG {number}    PLANTPULSE LAB    units: mm</text>')
    parts.append(f'<text x="708" y="802" font-family="monospace" font-size="11">Scale: {scale_note}; third-angle views</text>')
    parts.append('<text x="708" y="820" font-family="monospace" font-size="11">Gen. tol. +/-0.5 cut, +/-0.2 printed</text>')
    parts.append('<text x="708" y="840" font-family="monospace" font-size="10">Generated from plantpulse_cad.py - do not edit</text>')
    parts.append('<rect x="4" y="744" width="692" height="112" fill="white" stroke="black"/>')
    for i, line in enumerate(dims[:7]):
        parts.append(f'<text x="12" y="{760 + i * 14.5}" font-family="monospace" font-size="10.5">{line[:108]}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def bbox_dims(shape) -> str:
    bb = shape.val().BoundingBox() if isinstance(shape, cq.Workplane) else shape.BoundingBox()
    return f"{bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f}"


def svg_to_pdf(paths: list[Path]):
    """Convert SVG sheets to PDF and PNG previews with headless Chromium (node + playwright), if available."""
    import shutil
    import subprocess
    if not shutil.which("node"):
        return False
    script = Path(__file__).with_name("svg2pdf.js")
    r = subprocess.run(["node", str(script), *[str(p) for p in paths]], capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-400:])
    return r.returncode == 0


def main():
    for sub in ("step", "stl", "3mf", "dxf", "drawings"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)

    # ---- printed parts
    sheets = []
    for name, fn in m.PRINTED.items():
        shape = fn()
        exporters.export(shape, str(OUT / "step" / f"{name}.step"))
        exporters.export(shape, str(OUT / "stl" / f"{name}.stl"), tolerance=0.05, angularTolerance=0.2)
        exporters.export(shape, str(OUT / "3mf" / f"{name}.3mf"), tolerance=0.05, angularTolerance=0.2)
        vol = shape.val().Volume() / 1000
        p = OUT / "drawings" / f"{name}.svg"
        drawing_sheet(shape, name.replace("_", " "), name.split("_")[0],
                      [f"Envelope: {bbox_dims(shape)} mm", f"Volume: {vol:.1f} cm3 (PETG ~{vol * 1.27:.0f} g solid)",
                       "Material: PETG, 0.2 mm layers, 4 perimeters, 40 % infill",
                       "Hole sizes are clearance: M2.5 -> 2.8, M3 -> 3.4, M4 -> 4.3, M5 -> 5.3",
                       "See STEP file for all dimensions"], p, hidden=True)
        sheets.append(p)
        print("part", name, bbox_dims(shape), f"{vol:.1f} cm3")

    # ---- sheet parts as DXF
    t = m.P["tub"]
    sheet_parts = {
        "PP-M-022_lid": m.lid(),
        "PP-M-021_window": m.window(),
        "PP-M-010_floor_panel": m.box(m.CW, m.CD, 5),
        "PP-M-011_back_panel": m.box(m.CW + 10, m.MH - 2 * m.E + 10, 5),
        "PP-M-012_side_panel": m.box(m.CD + 10, m.MH - 2 * m.E + 10, 5),
        "PP-M-017_chamber_door": m.box(m.CW + 2 * m.E - 4, m.Z_MID - 4, 5),
        "PP-M-023_led_plate": m.box(m.CW - 20, m.CD - 20, 3),
    }
    for name, shape in sheet_parts.items():
        exporters.exportDXF(shape.section(), str(OUT / "dxf" / f"{name}.dxf"))
    lid_dims = [
        f"Lid 600 x 400 x {t['lid_t']:.0f}, matte black expanded PVC",
        f"6 x dia {t['net_pot_hole_d']:.0f} net-pot holes at x = {t['plant_cols_x']}, y = {t['plant_rows_y']}",
        "3 x dia 16 probe ports at x = 575, y = 120 / 200 / 280 (pH, EC, temperature)",
        "3 x dia 12.5 tube ports at x = 25, y = 150 / 200 / 250 (suction, air, return)",
        "2 x dia 22 at x = 575, y = 50 / 350 (top-up inlet, float switch)",
        "Datum: lid corner nearest gantry park, front edge",
        "Apply 4 ArUco fiducials (20 mm, DICT_4X4_50 ids 0-3) at 30 mm from each corner",
    ]
    p = OUT / "drawings" / "PP-M-022_lid.svg"
    drawing_sheet(m.lid(), "Tub lid / raft", "PP-M-022", lid_dims, p)
    sheets.append(p)

    # ---- pod assembly
    pod, bom = m.build_pod(with_plants=True)
    pod.save(str(OUT / "step" / "PP-A-001_pod_assembly.step"))
    comp = pod.toCompound()
    bb = comp.BoundingBox()
    pod_dims = [
        f"Pod envelope: {bb.xlen:.0f} W x {bb.ylen:.0f} D x {bb.zlen:.0f} H",
        f"Growth chamber interior: {m.CW:.0f} x {m.CD:.0f}; canopy clear height {m.P['pod']['canopy_clear_h']:.0f}",
        f"Lid top z = {m.Z_LID:.0f}; window underside z = {m.Z_WIN:.0f}; lens front z = {m.Z_LENS:.0f}",
        f"Plant pitch {t['plant_pitch']:.0f}; gantry stations x = {m.P['imaging']['stations_x']} (chamber coords)",
        f"Service bay width {m.SB:.0f}; frame 2020 6063-T5",
        "Doors: chamber, LED bay cover, service bay (front access only)",
        "Fasteners: M5 x 8 BHCS + T-nuts, corner brackets at every joint",
    ]
    wp = cq.Workplane(obj=comp)
    p = OUT / "drawings" / "PP-A-001_pod_assembly.svg"
    drawing_sheet(wp, "Pod assembly (general arrangement)", "PP-A-001", pod_dims, p)
    sheets.append(p)
    # open view without doors/panels for the internal arrangement
    pod_open, _ = m.build_pod(with_plants=True, gantry_x=m.P["imaging"]["stations_x"][1])
    keep = cq.Assembly(name="pod_open")
    for ch in pod_open.children:
        if re.match(r"PP-M-01[1-9]|PP-M-016", ch.name):
            continue
        keep.add(ch.obj, name=ch.name, loc=ch.loc, color=ch.color)
    p = OUT / "drawings" / "PP-A-002_pod_internal.svg"
    drawing_sheet(cq.Workplane(obj=keep.toCompound()), "Pod internal arrangement (panels removed, gantry at station 2)",
                  "PP-A-002", pod_dims, p)
    sheets.append(p)

    # ---- interference check on key bodies
    names = {c.name: c for c in pod.children}
    def solid(prefix):
        c = next(v for k, v in names.items() if k.startswith(prefix))
        return c.obj.val().moved(c.loc)
    checks = [("hq_camera", "PP-M-021_window"), ("PP-M-102_camera_mount", "PP-M-021_window"), ("tub", "ext2020_tub_support"),
              ("hq_camera", "lettuce_envelope"), ("mgn12h", "ext2020_gantry_beam"), ("led_strip", "PP-M-021_window"),
              ("topup_reservoir", "node_enclosure"), ("ptc_heater", "tub"), ("PP-M-107_sensor_shield", "tub")]
    lines = []
    for a_, b_ in checks:
        try:
            v = solid(a_).intersect(solid(b_)).Volume()
        except Exception as exc:  # noqa: BLE001
            v = float("nan")
            lines.append(f"{a_} vs {b_}: check failed ({exc})")
            continue
        lines.append(f"{a_} vs {b_}: intersection volume {v:.1f} mm3 -> {'CLASH' if v > 1.0 else 'clear'}")
    (OUT / "interference_report.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))

    # ---- rack
    rack, _ = m.build_rack()
    rack.save(str(OUT / "step" / "PP-A-000_rack_assembly.step"))
    rb = rack.toCompound().BoundingBox()
    p = OUT / "drawings" / "PP-A-000_rack_assembly.svg"
    drawing_sheet(cq.Workplane(obj=rack.toCompound()), "Facility rack: 4 pods (2 x 2)", "PP-A-000",
                  [f"Rack envelope: {rb.xlen:.0f} W x {rb.ylen:.0f} D x {rb.zlen:.0f} H",
                   "4 identical pods; lower pods on levelling feet; upper pods bolted through top rails",
                   "Power enclosure and central computer on right side",
                   f"Estimated wet mass per pod: see calculation report"], p)
    sheets.append(p)

    # ---- BOM
    with open(OUT / "bom_mechanical.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["part_no", "description", "material", "qty", "length_mm", "category"])
        w.writeheader()
        for r in sorted(bom.rows, key=lambda r: (r["part_no"], r["length_mm"] or 0)):
            w.writerow(r)
    total_ext = sum(r["qty"] * r["length_mm"] for r in bom.rows if r["category"] == "extrusion")
    print(f"BOM rows: {len(bom.rows)}; 2020 extrusion per pod: {total_ext / 1000:.2f} m")
    print("PDF sheets:", svg_to_pdf(sheets))


if __name__ == "__main__":
    main()
