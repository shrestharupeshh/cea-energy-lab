"""Generate the KiCad 7 schematic (.kicad_sch) for the PlantPulse Node from node_netlist.py.

Connectivity is expressed with global labels on every pin (no drawn wires), grouped by function.
The script then exports the schematic netlist with kicad-cli and compares it pin-by-pin with the
design netlist and with the PCB, so schematic, PCB and BOM cannot drift apart.
"""
from __future__ import annotations

import csv
import re
import subprocess
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import node_netlist as nl  # noqa: E402

SYM_ROOT = Path("/usr/share/kicad/symbols")
OUT = HERE / "plantpulse_node"
NS = uuid.UUID("7b0f1c9e-3c1d-4f0a-9d55-706c616e7470")


def uid(*parts) -> str:
    return str(uuid.uuid5(NS, "/".join(str(p) for p in parts)))


# ------------------------------------------------------------------ minimal s-expression reader/writer
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|\(|\)|[^\s()]+')


def parse(text: str):
    stack, cur = [], []
    for tok in TOKEN.findall(text):
        if tok == "(":
            stack.append(cur)
            cur = []
        elif tok == ")":
            done = cur
            cur = stack.pop()
            cur.append(done)
        else:
            cur.append(tok)
    return cur[0]


def dump(node, indent=0) -> str:
    if isinstance(node, str):
        return node
    flat = "(" + " ".join(dump(n) for n in node) + ")"
    if len(flat) < 110:
        return flat
    pad = "  " * (indent + 1)
    head = [n for n in node[:2] if isinstance(n, str)]
    rest = node[len(head):]
    return "(" + " ".join(head) + "".join("\n" + pad + dump(n, indent + 1) for n in rest) + "\n" + "  " * indent + ")"


def q(s) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


_LIB_CACHE: dict = {}


def load_symbol(lib_id: str):
    """Return (definition renamed to 'Lib:Name', pins) where pins = {number: (x, y, angle)}."""
    lib, name = lib_id.split(":")
    if lib not in _LIB_CACHE:
        _LIB_CACHE[lib] = parse((SYM_ROOT / f"{lib}.kicad_sym").read_text())
    tree = _LIB_CACHE[lib]
    syms = {n[1].strip('"'): n for n in tree if isinstance(n, list) and n[0] == "symbol"}
    node = syms[name]
    ext = next((n for n in node if isinstance(n, list) and n[0] == "extends"), None)
    if ext is not None:
        parent_name = ext[1].strip('"')
        parent = syms[parent_name]
        body = []
        for n in parent:
            if isinstance(n, list) and n[0] == "symbol":
                sub = [x for x in n]
                sub[1] = q(sub[1].strip('"').replace(parent_name, name, 1))
                body.append(sub)
            elif isinstance(n, list) and n[0] == "property":
                continue
            elif isinstance(n, list):
                body.append(n)
        props = [n for n in node if isinstance(n, list) and n[0] == "property"]
        node = ["symbol", q(name)] + [b for b in body if b[0] != "symbol"] + props + [b for b in body if b[0] == "symbol"]
    node = list(node)
    node[1] = q(lib_id)
    pins, units = {}, set()

    def walk(n, unit=None):
        if not isinstance(n, list):
            return
        if n[0] == "symbol" and n is not node:
            m = re.match(r".*_(\d+)_(\d+)$", n[1].strip('"'))
            unit = int(m.group(1)) if m else None
            if unit:
                units.add(unit)
        if n[0] == "pin":
            at = next(x for x in n if isinstance(x, list) and x[0] == "at")
            num = next(x for x in n if isinstance(x, list) and x[0] == "number")[1].strip('"')
            pins[num] = (float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0)
        for c in n:
            walk(c, unit)

    walk(node)
    if len(units) > 1:
        raise RuntimeError(f"{lib_id} has {len(units)} units; generator supports single-unit symbols only")
    return node, pins


LABEL_ANGLE = {0: 180, 180: 0, 90: 270, 270: 90}
GROUP_TITLES = {
    "power": "POWER ENTRY, PROTECTION, REGULATION", "mcu": "MCU SOCKET (ESP32-S3-DevKitC-1) AND BUS PULL-UPS",
    "outputs": "FAIL-SAFE OUTPUT BUFFER AND LOW-SIDE SWITCHES", "fans": "PWM FANS",
    "motion": "GANTRY STEPPER", "sensors": "SENSOR CONNECTORS", "inputs": "I/O EXPANDER AND SWITCH INPUTS",
}


def build() -> str:
    lib_defs, placed, labels, ncs, texts = {}, [], [], [], []
    root = uid("root")
    # layout: groups in rows across an A1 sheet (841 x 594)
    cell_w = 58.42
    y_cursor = 25.4
    for group, title in GROUP_TITLES.items():
        parts = [p for p in nl.PARTS if p.sheet == group]
        if not parts:
            continue
        texts.append((12.7, y_cursor - 5.08, title))
        x, row_h = 38.1, 0.0
        for p in parts:
            lib_id = nl.SYM[p.kind]
            if lib_id not in lib_defs:
                lib_defs[lib_id] = load_symbol(lib_id)
            _, pins = lib_defs[lib_id]
            ys = [v[1] for v in pins.values()] or [0]
            h = max(ys) - min(ys) + 22.86
            if x + cell_w > 820:
                x = 38.1
                y_cursor += row_h
                row_h = 0.0
            sx = round(x / 1.27) * 1.27
            sy = round((y_cursor + (max(ys) + 10.16)) / 1.27) * 1.27
            placed.append((p, lib_id, sx, sy))
            for num, (px, py, ang) in pins.items():
                net = p.pins.get(num, "")
                lx, ly = round(sx + px, 4), round(sy - py, 4)
                if net:
                    labels.append((net, lx, ly, LABEL_ANGLE[int(ang) % 360], p.ref, num))
                else:
                    ncs.append((lx, ly, p.ref, num))
            x += cell_w
            row_h = max(row_h, h)
        y_cursor += row_h + 12.7

    out = ['(kicad_sch (version 20230121) (generator "plantpulse_generate_schematic")', f'  (uuid {root})', '  (paper "A1")',
           '  (title_block (title "PlantPulse Node carrier board") (rev "A") (company "PLANTPULSE LAB")'
           ' (comment 1 "Generated from node_netlist.py - connectivity by global labels") (comment 2 "PP-E-001, CERN-OHL-P-2.0"))',
           "  (lib_symbols"]
    for lib_id, (node, _) in lib_defs.items():
        out.append("    " + dump(node, 2))
    out.append("  )")
    for x, y, title in texts:
        out.append(f'  (text {q(title)} (at {x} {y} 0) (effects (font (size 2.54 2.54) bold) (justify left bottom)) (uuid {uid("t", title)}))')
    for p, lib_id, sx, sy in placed:
        lib, fp = nl.FP[p.kind]
        out.append(f'  (symbol (lib_id {q(lib_id)}) (at {sx} {sy} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid {uid("s", p.ref)})')
        out.append(f'    (property "Reference" {q(p.ref)} (at {sx} {sy - 2.54} 0) (effects (font (size 1.27 1.27))))')
        out.append(f'    (property "Value" {q(p.value)} (at {sx} {sy + 2.54} 0) (effects (font (size 1.27 1.27))))')
        out.append(f'    (property "Footprint" {q(lib + ":" + fp)} (at {sx} {sy} 0) (effects (font (size 1.27 1.27)) hide))')
        out.append(f'    (property "Datasheet" "~" (at {sx} {sy} 0) (effects (font (size 1.27 1.27)) hide))')
        out.append(f'    (property "MPN" {q(p.mpn)} (at {sx} {sy} 0) (effects (font (size 1.27 1.27)) hide))')
        out.append(f'    (property "Description" {q(p.desc)} (at {sx} {sy} 0) (effects (font (size 1.27 1.27)) hide))')
        for num in lib_defs[lib_id][1]:
            out.append(f'    (pin {q(num)} (uuid {uid("p", p.ref, num)}))')
        out.append(f'    (instances (project "plantpulse_node" (path "/{root}" (reference {q(p.ref)}) (unit 1))))')
        out.append("  )")
    for net, x, y, ang, ref, num in labels:
        just = "right" if ang in (180, 270) else "left"
        out.append(f'  (global_label {q(net)} (shape passive) (at {x} {y} {ang}) (effects (font (size 1.0 1.0)) (justify {just}))'
                   f' (uuid {uid("l", ref, num)}))')
    for x, y, ref, num in ncs:
        out.append(f'  (no_connect (at {x} {y}) (uuid {uid("nc", ref, num)}))')
    out.append('  (sheet_instances (path "/" (page "1")))')
    out.append(")")
    return "\n".join(out) + "\n"


def write_project():
    pro = OUT / "plantpulse_node.kicad_pro"
    if not pro.exists():
        pro.write_text('{\n  "meta": {"filename": "plantpulse_node.kicad_pro", "version": 1}\n}\n')


def verify(sch: Path) -> list[str]:
    """Compare schematic netlist (as KiCad reads it) with the design netlist and with the PCB."""
    net_file = OUT / "plantpulse_node.net"
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", str(net_file), str(sch)], check=True, capture_output=True)
    tree = parse(net_file.read_text())
    nets_node = next(n for n in tree if isinstance(n, list) and n[0] == "nets")
    sch_nets = {}
    for n in nets_node[1:]:
        name = next(x for x in n if isinstance(x, list) and x[0] == "name")[1].strip('"').lstrip("/")
        pins = set()
        for x in n:
            if isinstance(x, list) and x[0] == "node":
                ref = next(y for y in x if isinstance(y, list) and y[0] == "ref")[1].strip('"')
                pin = next(y for y in x if isinstance(y, list) and y[0] == "pin")[1].strip('"')
                pins.add((ref, pin))
        sch_nets[name] = pins
    design = {k: set(v) for k, v in nl.nets().items()}
    problems = []
    for name, pins in design.items():
        if sch_nets.get(name) != pins:
            problems.append(f"schematic net {name}: missing {sorted(pins - sch_nets.get(name, set()))} extra {sorted(sch_nets.get(name, set()) - pins)}")
    for name in sch_nets:
        if name not in design and not name.startswith("unconnected-"):
            problems.append(f"schematic has undeclared net {name}")
    try:
        import pcbnew
        board = pcbnew.LoadBoard(str(OUT / "plantpulse_node.kicad_pcb"))
        pcb = {}
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetname():
                    pcb.setdefault(pad.GetNetname(), set()).add((fp.GetReference(), pad.GetNumber()))
        for name, pins in design.items():
            if pcb.get(name) != pins:
                problems.append(f"PCB net {name} differs from design netlist")
    except ImportError:
        problems.append("pcbnew not available: PCB comparison skipped")
    return problems


def write_bom():
    groups = {}
    for p in nl.PARTS:
        key = (p.value, p.kind, p.mpn)
        groups.setdefault(key, []).append(p)
    with open(OUT / "plantpulse_node_bom.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["qty", "references", "value", "footprint", "mpn", "description"])
        for (value, kind, mpn), ps in sorted(groups.items(), key=lambda kv: kv[1][0].ref):
            w.writerow([len(ps), " ".join(p.ref for p in ps), value, nl.FP[kind][1], mpn, ps[0].desc])


def main():
    OUT.mkdir(exist_ok=True)
    write_project()
    sch = OUT / "plantpulse_node.kicad_sch"
    sch.write_text(build())
    subprocess.run(["kicad-cli", "sch", "export", "pdf", "-o", str(OUT / "plantpulse_node_schematic.pdf"), str(sch)],
                   check=True, capture_output=True)
    write_bom()
    problems = verify(sch)
    report = OUT / "netlist_consistency.txt"
    report.write_text("Schematic vs design netlist vs PCB: " + ("CONSISTENT\n" if not problems else "MISMATCH\n" + "\n".join(problems) + "\n"))
    print(report.read_text())
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
