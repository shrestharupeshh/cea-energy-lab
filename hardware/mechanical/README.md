# Mechanical design

Parametric CAD in CadQuery (OpenCASCADE kernel). SolidWorks and FreeCAD were not available in the
build environment; the STEP assemblies import into both with the assembly tree and colours intact.
Every dimension is driven by `hardware/design_parameters.yaml`.

```
python hardware/mechanical/cad/build_all.py     # regenerates everything under output/
python -m plantpulse.engineering.report         # regenerates calculations/
```

## Outputs

| Path | Content |
|------|---------|
| `output/step/PP-A-000_rack_assembly.step` | 4-pod rack |
| `output/step/PP-A-001_pod_assembly.step` | one pod, all components |
| `output/step/PP-M-1xx_*.step`, `output/stl/`, `output/3mf/` | 10 printed parts |
| `output/dxf/` | sheet parts for laser/CNC (lid, window, panels, LED plate) |
| `output/drawings/*.svg, *.pdf, *.png` | assembly and part sheets (4 views + data block) |
| `output/bom_mechanical.csv` | cut list and part counts extracted from the model |
| `output/interference_report.txt` | boolean clash checks on critical pairs |
| `calculations/calculation_report.md` | structural, hydraulic, lighting, thermal, imaging, electrical calculations |

Drawing sheets are generated views with principal dimensions in the data block. They are adequate
for cutting sheet parts (use the DXF) and printing (use the STL/3MF); they are not fully
dimensioned GD&T drawings. Fully detailed drawings should be produced from the STEP files in
SolidWorks before any outsourced machining.

## Design description

1. **Structural enclosure**: 2020 6063-T5 T-slot frame, 1040 x 540 x 880 mm per pod (18.0 m of
   extrusion), M5 T-nuts and cast corner brackets, 5 mm white expanded-PVC panels in the slots
   (reflective, closed-cell, wipe-clean). Pods stack two high on levelling feet.
2. **Growing tray**: 600 x 400 x 170 mm Euro container as a deep-water-culture tub, 28 L at 120 mm
   depth, on two cross-members (0.55 mm deflection, safety factor 10 on yield). Matte-black 6 mm
   lid with six 51 mm net-pot holes on a 200 mm pitch and probe/tube ports. Two fiducial bars (PP-M-024)
   beside the tub carry eight ArUco markers outside the reach of the canopy.
3. **Reservoir mounting**: 5 L top-up reservoir in the service bay on a printed cradle and one bar
   load cell, on a two-rail shelf (0.06 mm deflection).
4. **Plumbing**: tub → suction port → circulation pump (bay floor, below water line, flooded
   suction) → flow meter → return port with spray bar. Top-up: reservoir → peristaltic pump →
   lid port. Air line from the rack air pump to an air stone. 8 mm ID silicone tubing, all
   connections above the tub rim except the suction bulkhead; drip tray under the bay.
5. **Pump mounting**: pump on a rubber-isolated plate on the bay floor; peristaltic pump on the
   partition panel.
6. **LED mounting**: strips on the underside of a 3 mm aluminium heat-spreader plate under the top
   ring, above a 3 mm acrylic window; the LED bay has its own fan and exchanges air with the room
   only.
7. **Camera mount**: printed bracket (PP-M-102) on a 2020 cantilever arm; HQ camera, Pi Zero 2 W
   and LED ring move together.
8. **Imaging gantry**: MGN12H carriage on a 700 mm rail on the back-wall beam, GT2 belt, NEMA17,
   microswitch home. Three stations over the plant columns plus a park position outside the
   canopy. Arm tip static deflection 0.04 mm; station repeatability budget 0.075 mm (1 σ).
9. **Electronics enclosure**: IP65 ABS box high in the dry service bay, glands downward.
10. **Maintenance access**: everything from the front: chamber door, LED-bay cover, service-bay
    door. Tub slides out forward on the floor panel after lifting the lid's probe bushings.

## Known mechanical open items

- Door hinge, magnetic latch, gasket and cable-gland cut-outs are specified in the BOM but not
  modelled as features in the panels.
- Light-trap loss coefficient is an estimate; airflow must be measured (VAL-ENV-04).
- Tubing runs and wiring harness are not modelled.
- Printed parts have not been printed or fit-checked.
- The Euro container model is a simplified envelope; check lid fit on the purchased container
  before cutting four lids.
