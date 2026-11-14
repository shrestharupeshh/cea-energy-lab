# Paper 1 (working title): An open, replicated-unit platform and longitudinal multimodal dataset for lettuce phenotyping under controlled environments

Status: outline. Sections marked [DATA] cannot be written until the named runs exist.

1. **Introduction** - gap from `docs/research/literature_review.md` section 7: no open platform combining
   independent replicated environments, automated per-plant imaging, synchronised environment and
   destructive ground truth; cross-sectional nature of existing lettuce datasets.
2. **Platform design** - requirements traceable to hypotheses (`docs/requirements`), pod architecture and the
   pseudoreplication argument, lighting/thermal/hydraulic design with calculations, imaging gantry and
   fiducial bars, electronics and fail-safe design, software and data architecture, cost (BOM).
3. **Validation methods** - `docs/validation/validation_plan.md` (criteria fixed in advance), calibration
   chain to traceable references, uncertainty budget.
4. **Results** [DATA: validation tests A-F; U1-U2; B1-B2]
   - 4.1 Sensor accuracy and drift; 4.2 environmental control and pod equivalence;
   - 4.3 PPFD maps; 4.4 imaging repeatability and geometric accuracy;
   - 4.5 uniformity trials: variance components, ICC_pod, per-pod BLUPs (H5a);
   - 4.6 vision traits vs manual/destructive: bias, limits of agreement, CCC (H2a-b);
   - 4.7 data completeness and QC statistics (H5c).
5. **Dataset description** [DATA] - structure, identifiers, QC flags, licences, known limitations
   (per-plant area unreliable after canopy closure; lid-plane scale; single cultivar).
6. **Discussion** - what the platform can and cannot support (no cooling below room, no CO2 enrichment,
   n = 4 units per run), cost vs commercial chambers, lessons from the simulated rehearsal that changed the
   design (fiducial placement, humidifier sizing, alarm rule), replication invitation.
7. **Availability** - repository tag, dataset DOI, hardware licence.

Figures (scripts in `publications/figures/make_figures.py`; placeholders use design/simulated data and are watermarked):
F1 pod CAD cut-away; F2 architecture diagram; F3 PPFD map measured vs simulated; F4 control traces;
F5 variance components; F6 Bland-Altman panels; F7 example image series with masks.
Tables: T1 requirements vs achieved; T2 BOM summary; T3 acceptance results; T4 dataset summary.
