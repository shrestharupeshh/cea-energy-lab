"""Generate the PlantPulse Node PCB (KiCad 7 .kicad_pcb) from node_netlist.py.

Pipeline: place footprints -> assign nets -> route with a built-in grid A* router (two layers,
through vias, per-net track widths with automatic neck-down) -> GND pours on both layers ->
KiCad DRC report. Run with the system Python that has the `pcbnew` module:

    python3 hardware/electrical/pcb/generate_pcb.py

The router is deliberately simple (no rip-up). The KiCad DRC report written next to the board is
the authority on whether the result is manufacturable; read it before ordering boards.
"""
from __future__ import annotations

import heapq
import math
import sys
from pathlib import Path

import cv2
import numpy as np
import pcbnew

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import node_netlist as nl  # noqa: E402

FP_ROOT = Path("/usr/share/kicad/footprints")
OUT = HERE / "plantpulse_node"
G = 0.254                 # routing grid (mm)
SUB = 5                   # fine raster pixels per grid cell
PX = G / SUB              # fine raster pitch (mm)
VIA_D, VIA_DRILL = 0.8, 0.4
MARGIN = 0.07             # extra clearance to absorb grid quantisation
EDGE_KEEPOUT = 0.6
OX, OY = nl.ORIGIN
NX, NY = int(round(nl.BOARD_W / G)) + 1, int(round(nl.BOARD_H / G)) + 1
mm = pcbnew.FromMM


def snap(v: float) -> float:
    return round(v / 1.27) * 1.27


def vec(x, y):
    return pcbnew.VECTOR2I(mm(x + OX), mm(y + OY))


# --------------------------------------------------------------------------- board construction
def build_board():
    board = pcbnew.BOARD()
    bds = board.GetDesignSettings()
    bds.m_TrackMinWidth = mm(0.2)
    bds.m_ViasMinSize = mm(0.6)
    bds.m_MinClearance = mm(0.2)
    bds.m_CopperEdgeClearance = mm(0.4)
    nets = {"": board.FindNet(0)}
    for name in nl.nets():
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
        nets[name] = n
    pads = []      # dict(ref, num, net, x, y, r, sx, sy, th)
    for p in nl.PARTS:
        lib, name = nl.FP[p.kind]
        fp = pcbnew.FootprintLoad(str(FP_ROOT / f"{lib}.pretty"), name)
        if fp is None:
            raise RuntimeError(f"footprint not found: {lib}:{name}")
        fp.SetReference(p.ref)
        fp.SetValue(p.value)
        fp.SetPosition(vec(snap(p.x), snap(p.y)))
        fp.SetOrientationDegrees(p.rot)
        board.Add(fp)
        for pad in fp.Pads():
            num = pad.GetNumber()
            net = p.pins.get(num, "")
            if net:
                pad.SetNet(nets[net])
            pos = pad.GetPosition()
            size = pad.GetSize()
            pads.append({
                "ref": p.ref, "num": num, "net": net,
                "x": pcbnew.ToMM(pos.x) - OX, "y": pcbnew.ToMM(pos.y) - OY,
                "sx": pcbnew.ToMM(size.x), "sy": pcbnew.ToMM(size.y),
                "rot": pad.GetOrientationDegrees(),
                "th": pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH),
                "drill": pcbnew.ToMM(pad.GetDrillSize().x),
                "rect": pad.GetShape() in (pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_ROUNDRECT, pcbnew.PAD_SHAPE_TRAPEZOID),
                "bbox": (pcbnew.ToMM(pad.GetBoundingBox().GetLeft()) - OX, pcbnew.ToMM(pad.GetBoundingBox().GetTop()) - OY,
                         pcbnew.ToMM(pad.GetBoundingBox().GetRight()) - OX, pcbnew.ToMM(pad.GetBoundingBox().GetBottom()) - OY),
            })
    for (x, y) in nl.MOUNT_HOLES:
        lib, name = nl.FP["HOLE"]
        fp = pcbnew.FootprintLoad(str(FP_ROOT / f"{lib}.pretty"), name)
        fp.SetReference(f"H{len(pads)}")
        fp.Reference().SetVisible(False)
        fp.SetPosition(vec(x, y))
        board.Add(fp)
        pads.append({"ref": "H", "num": "", "net": "", "x": x, "y": y, "sx": 6.4, "sy": 6.4, "rot": 0, "th": True, "drill": 3.2})
    edge = pcbnew.PCB_SHAPE(board)
    edge.SetShape(pcbnew.SHAPE_T_RECT)
    edge.SetStart(vec(0, 0))
    edge.SetEnd(vec(nl.BOARD_W, nl.BOARD_H))
    edge.SetLayer(pcbnew.Edge_Cuts)
    edge.SetWidth(mm(0.1))
    board.Add(edge)
    for i, text in enumerate(["PLANTPULSE NODE  PP-E-001 rev A", "CERN-OHL-P-2.0   SELV only: 24 V DC max"]):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetPosition(vec(146, 96.5 + i * 2.6))
        t.SetLayer(pcbnew.F_SilkS)
        t.SetTextSize(pcbnew.VECTOR2I(mm(1.2), mm(1.2)))
        t.SetTextThickness(mm(0.15))
        board.Add(t)
    return board, nets, pads


# --------------------------------------------------------------------------- copper model for the router
class Copper:
    """Vector list of copper primitives; rasterised on demand into clearance maps."""

    def __init__(self, pads):
        self.items = []   # (layer or -1, net, kind, geom)
        for p in pads:
            lyr = -1 if p["th"] else 0
            long_, short = max(p["sx"], p["sy"]), min(p["sx"], p["sy"])
            if p.get("rect"):
                self.items.append((lyr, p["net"], "r", p["bbox"]))
            elif long_ - short < 0.05:
                self.items.append((lyr, p["net"], "c", (p["x"], p["y"], long_ / 2 * (1.0 if p["th"] else 1.2))))
            else:
                ang = math.radians(-p["rot"]) + (0 if p["sx"] >= p["sy"] else math.pi / 2)
                dx, dy = math.cos(ang) * (long_ - short) / 2, math.sin(ang) * (long_ - short) / 2
                self.items.append((lyr, p["net"], "s", (p["x"] - dx, p["y"] - dy, p["x"] + dx, p["y"] + dy, short / 2 * 1.15)))

    def add_track(self, layer, net, x1, y1, x2, y2, w):
        self.items.append((layer, net, "s", (x1, y1, x2, y2, w / 2)))

    def add_via(self, net, x, y):
        self.items.append((-1, net, "c", (x, y, VIA_D / 2)))

    def distance_maps(self, net):
        """Distance (mm) from every grid cell to the nearest copper of any other net, per layer."""
        h, w = (NY - 1) * SUB + 1, (NX - 1) * SUB + 1
        out = []
        for layer in (0, 1):
            img = np.full((h, w), 255, np.uint8)
            for lyr, n, kind, g in self.items:
                if n == net and net != "":
                    continue
                if lyr not in (-1, layer):
                    continue
                if kind == "r":
                    cv2.rectangle(img, (int(math.floor(g[0] / PX)), int(math.floor(g[1] / PX))),
                                  (int(math.ceil(g[2] / PX)), int(math.ceil(g[3] / PX))), 0, -1)
                elif kind == "c":
                    cv2.circle(img, (int(round(g[0] / PX)), int(round(g[1] / PX))), max(int(round(g[2] / PX)), 1), 0, -1)
                else:
                    th = max(int(round(2 * g[4] / PX)), 1)
                    cv2.line(img, (int(round(g[0] / PX)), int(round(g[1] / PX))), (int(round(g[2] / PX)), int(round(g[3] / PX))), 0, th)
            k = int(round(EDGE_KEEPOUT / PX))
            img[:k, :] = 0
            img[-k:, :] = 0
            img[:, :k] = 0
            img[:, -k:] = 0
            dist = cv2.distanceTransform(img, cv2.DIST_L2, 5) * PX
            out.append(dist[::SUB, ::SUB])
        return out


SQ2 = math.sqrt(2)
MOVES = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, SQ2), (1, -1, SQ2), (-1, 1, SQ2), (-1, -1, SQ2)]


def astar(free, via_ok, starts, targets, tpts, via_cost=14.0, max_nodes=900_000):
    """free[layer][iy, ix] bool; starts: list of (layer, iy, ix); targets: bool arrays per layer;
    tpts: array of (iy, ix) points used for the heuristic."""
    tp = np.asarray(tpts, float)

    def h(iy, ix):
        d = np.abs(tp - (iy, ix))
        mn, mx = d.min(axis=1), d.max(axis=1)
        return float(((mx - mn) + SQ2 * mn).min())

    openq = []
    best = {}
    for s in starts:
        best[s] = 0.0
        heapq.heappush(openq, (1.2 * h(s[1], s[2]), 0.0, s, None))
    came = {}
    n = 0
    while openq:
        f, g, node, parent = heapq.heappop(openq)
        if node in came:
            continue
        came[node] = parent
        l, iy, ix = node
        if targets[l][iy, ix]:
            path = [node]
            while came[path[-1]] is not None:
                path.append(came[path[-1]])
            return path[::-1]
        n += 1
        if n > max_nodes:
            return None
        fl = free[l]
        for dy, dx, c in MOVES:
            y2, x2 = iy + dy, ix + dx
            if not (0 <= y2 < NY and 0 <= x2 < NX) or not (fl[y2, x2] or targets[l][y2, x2]):
                continue
            if dy and dx and not (fl[iy, x2] and fl[y2, ix]):
                continue
            # layer direction bias: top prefers horizontal, bottom prefers vertical
            bias = 1.0 if (l == 0 and dy == 0) or (l == 1 and dx == 0) else (1.25 if dy and dx else 1.6)
            ng = g + c * bias
            nn = (l, y2, x2)
            if ng < best.get(nn, 1e18):
                best[nn] = ng
                heapq.heappush(openq, (ng + 1.2 * h(y2, x2), ng, nn, node))
        if via_ok[iy, ix]:
            nn = (1 - l, iy, ix)
            ng = g + via_cost
            if ng < best.get(nn, 1e18):
                best[nn] = ng
                heapq.heappush(openq, (ng + 1.2 * h(iy, ix), ng, nn, node))
    return None


def cell(x, y):
    return int(round(y / G)), int(round(x / G))


def route_all(board, nets, pads, log):
    copper = Copper(pads)
    by_net = {}
    for p in pads:
        if p["net"]:
            by_net.setdefault(p["net"], []).append(p)

    def span(ps):
        xs, ys = [q["x"] for q in ps], [q["y"] for q in ps]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))

    order = sorted(by_net, key=lambda n: (-nl.NET_WIDTH.get(n, nl.SIGNAL_W) >= -1.0, span(by_net[n])))
    order = sorted(by_net, key=lambda n: (2 if n == "GND" else 0 if nl.NET_WIDTH.get(n, nl.SIGNAL_W) >= 2.0 else 1, span(by_net[n])))
    failed, necked, total_len, n_vias = [], [], 0.0, 0
    th_cells = {}
    for p in pads:
        if p["th"]:
            th_cells[cell(p["x"], p["y"])] = p["net"]

    for net in order:
        ps = by_net[net]
        w_nom = nl.NET_WIDTH.get(net, nl.SIGNAL_W)
        dmaps = copper.distance_maps(net)
        # tree = cells already belonging to this net
        tree = [np.zeros((NY, NX), bool), np.zeros((NY, NX), bool)]
        tpts = []

        def add_pad_to_tree(p):
            iy, ix = cell(p["x"], p["y"])
            for l in ((0, 1) if p["th"] else (0,)):
                tree[l][iy, ix] = True
            tpts.append((iy, ix))

        remaining = sorted(ps, key=lambda q: (q["x"], q["y"]))
        add_pad_to_tree(remaining.pop(0))
        while remaining:
            # nearest remaining pad to the tree
            tp = np.asarray(tpts, float)
            remaining.sort(key=lambda q: float(np.abs(tp - cell(q["x"], q["y"])).sum(axis=1).min()))
            p = remaining.pop(0)
            done = False
            for w in [w_nom] + [x for x in (1.2, 0.8, 0.5, 0.3) if x < w_nom]:
                need = w / 2 + nl.CLEARANCE + MARGIN
                free = [dm >= need for dm in dmaps]
                vneed = max(w, VIA_D) / 2 + nl.CLEARANCE + MARGIN
                via_ok = (dmaps[0] >= vneed) & (dmaps[1] >= vneed)
                iy, ix = cell(p["x"], p["y"])
                starts = [(l, iy, ix) for l in ((0, 1) if p["th"] else (0,))]
                for l, y_, x_ in starts:
                    free[l][y_, x_] = True
                path = astar(free, via_ok, starts, tree, tpts)
                if path:
                    if w < w_nom:
                        necked.append((net, p["ref"], p["num"], w))
                    done = True
                    break
            if not done:
                failed.append((net, p["ref"], p["num"]))
                add_pad_to_tree(p)      # keep going with the rest of the net
                continue
            # emit tracks
            netinfo = nets[net]
            pts = [(l, x_ * G, y_ * G) for l, y_, x_ in path]
            # stub from exact pad centre to first grid point, and to the exact pad centre at the far end if any
            seq = [(pts[0][0], p["x"], p["y"])] + pts
            end = path[-1]
            for q in ps:
                if cell(q["x"], q["y"]) == (end[1], end[2]):
                    seq.append((pts[-1][0], q["x"], q["y"]))
                    break
            i = 0
            while i < len(seq) - 1:
                l, x1, y1 = seq[i]
                l2, x2, y2 = seq[i + 1]
                if l2 != l:
                    if (int(round(y1 / G)), int(round(x1 / G))) not in th_cells:
                        v = pcbnew.PCB_VIA(board)
                        v.SetPosition(vec(x1, y1))
                        v.SetWidth(mm(VIA_D))
                        v.SetDrill(mm(VIA_DRILL))
                        v.SetViaType(pcbnew.VIATYPE_THROUGH)
                        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                        v.SetNet(netinfo)
                        board.Add(v)
                        copper.add_via(net, x1, y1)
                        n_vias += 1
                    i += 1
                    continue
                # extend collinear run
                j = i + 1
                while j + 1 < len(seq) and seq[j + 1][0] == l:
                    ax, ay = seq[j][1] - seq[i][1], seq[j][2] - seq[i][2]
                    bx, by = seq[j + 1][1] - seq[j][1], seq[j + 1][2] - seq[j][2]
                    if abs(ax * by - ay * bx) > 1e-9 or ax * bx + ay * by <= 0:
                        break
                    j += 1
                x2, y2 = seq[j][1], seq[j][2]
                if abs(x2 - x1) + abs(y2 - y1) > 1e-6:
                    t = pcbnew.PCB_TRACK(board)
                    t.SetStart(vec(x1, y1))
                    t.SetEnd(vec(x2, y2))
                    t.SetWidth(mm(w))
                    t.SetLayer(pcbnew.F_Cu if l == 0 else pcbnew.B_Cu)
                    t.SetNet(netinfo)
                    board.Add(t)
                    copper.add_track(l, net, x1, y1, x2, y2, w)
                    total_len += math.hypot(x2 - x1, y2 - y1)
                i = j
            for l, y_, x_ in path:
                tree[l][y_, x_] = True
            tpts.extend((y_, x_) for _, y_, x_ in path[:: max(len(path) // 12, 1)])
            add_pad_to_tree(p)
        log(f"routed {net:16s} pins={len(ps):2d} width={w_nom}")
    return failed, necked, total_len, n_vias


def add_ground_pours(board, nets):
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(nets["GND"])
        z.SetLocalClearance(mm(0.3))
        z.SetMinThickness(mm(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)   # GND is also routed as tracks; solid pour avoids starved thermals
        z.SetThermalReliefGap(mm(0.3))
        z.SetThermalReliefSpokeWidth(mm(0.5))
        o = z.Outline()
        o.NewOutline()
        for x, y in ((0.5, 0.5), (nl.BOARD_W - 0.5, 0.5), (nl.BOARD_W - 0.5, nl.BOARD_H - 0.5), (0.5, nl.BOARD_H - 0.5)):
            o.Append(mm(x + OX), mm(y + OY))
        board.Add(z)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def main():
    problems = nl.check()
    if problems:
        raise SystemExit("netlist problems: " + "; ".join(problems))
    OUT.mkdir(exist_ok=True)
    board, nets, pads = build_board()
    lines = []
    failed, necked, length, n_vias = route_all(board, nets, pads, lines.append)
    pcb_path = OUT / "plantpulse_node.kicad_pcb"
    print("routing done; saving", flush=True)
    pcbnew.SaveBoard(str(pcb_path), board)
    if "--no-pour" not in sys.argv:
        # Reload from disk before pouring: filling zones on a board that only exists in memory is
        # unstable in the KiCad 7 Python API.
        board = pcbnew.LoadBoard(str(pcb_path))
        gnd = {"GND": board.FindNet("GND")}
        print("pouring ground", flush=True)
        add_ground_pours(board, gnd)
        pcbnew.SaveBoard(str(pcb_path), board)
    summary = [
        f"parts: {len(nl.PARTS)}  nets: {len(nl.nets())}  pads: {len(pads)}",
        f"routed track length: {length:.0f} mm, vias: {n_vias}",
        f"connections the router could not complete: {len(failed)}",
        *[f"  UNROUTED {n} at {r}.{p}" for n, r, p in failed],
        f"connections routed below nominal width (neck-down): {len(necked)}",
        *[f"  {n} at {r}.{p}: {w} mm" for n, r, p, w in necked],
    ]
    (OUT / "routing_report.txt").write_text("\n".join(summary + [""] + lines) + "\n")
    print("\n".join(summary))
    print("saved", pcb_path)


if __name__ == "__main__":
    main()
