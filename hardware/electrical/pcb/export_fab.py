"""Run KiCad DRC on the generated board and export fabrication outputs (Gerber, drill, position, renders)."""
import subprocess
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).parent
PCB = HERE / "plantpulse_node" / "plantpulse_node.kicad_pcb"
FAB = HERE / "plantpulse_node" / "fab"


def main():
    board = pcbnew.LoadBoard(str(PCB))
    rpt = PCB.with_name("drc_report.txt")
    pcbnew.WriteDRCReport(board, str(rpt), pcbnew.EDA_UNITS_MILLIMETRES, True)
    text = rpt.read_text()
    counts = {}
    for line in text.splitlines():
        if line.startswith("["):
            k = line[1:line.index("]")]
            counts[k] = counts.get(k, 0) + 1
    print("DRC item counts:", counts or "none")
    for marker in ("** Found", "unconnected"):
        for line in text.splitlines():
            if marker in line:
                print(line.strip())
    if "--drc-only" in sys.argv:
        return
    (FAB / "gerber").mkdir(parents=True, exist_ok=True)
    layers = "F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts,F.Fab"
    run = lambda *a: subprocess.run(["kicad-cli", *a], check=True, capture_output=True)
    run("pcb", "export", "gerbers", "-o", str(FAB / "gerber") + "/", "-l", layers, str(PCB))
    run("pcb", "export", "drill", "-o", str(FAB / "gerber") + "/", "--format", "excellon", "--excellon-separate-th",
        "--generate-map", "--map-format", "pdf", str(PCB))
    run("pcb", "export", "pos", "-o", str(FAB / "plantpulse_node-pos.csv"), "--format", "csv", "--units", "mm", str(PCB))
    run("pcb", "export", "svg", "-o", str(FAB / "plantpulse_node_top.svg"), "-l", "F.Cu,F.SilkS,Edge.Cuts", "--page-size-mode", "2", "--exclude-drawing-sheet", str(PCB))
    run("pcb", "export", "svg", "-o", str(FAB / "plantpulse_node_bottom.svg"), "-l", "B.Cu,Edge.Cuts", "--page-size-mode", "2", "--exclude-drawing-sheet", "--mirror", str(PCB))
    run("pcb", "export", "pdf", "-o", str(FAB / "plantpulse_node_assembly.pdf"), "-l", "F.Fab,F.SilkS,Edge.Cuts", str(PCB))
    run("pcb", "export", "step", "-o", str(FAB / "plantpulse_node.step"), "--subst-models", "--force", str(PCB))
    print("fabrication outputs in", FAB)


if __name__ == "__main__":
    main()
