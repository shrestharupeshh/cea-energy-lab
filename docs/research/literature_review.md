# Literature review and research gap

Status: Phase 1 working review, compiled 2026-11. It is a scoping review, not a systematic review.
Sources were located by targeted web searches plus the team's prior knowledge. Each entry in
`literature_matrix.csv` carries a `verification_status` column: entries marked "cited from memory"
or "to be confirmed" **must be opened and checked (DOI, authors, numbers) before they are cited in
any manuscript**. Numbers quoted below are as reported by the cited authors or by search snippets
and have not been independently reproduced.

A formal PRISMA-style search (Scopus + Web of Science + CAB Abstracts) is scheduled as task
LIT-02 before Paper 1 submission; the search strings are in section 6.

## 1. Low-cost phenotyping hardware

Raspberry Pi cameras in growth chambers are an established low-cost phenotyping route (Tovar et al.
2018, L10; Phenotiki, L12), and PlantCV (L11) provides open classical pipelines. These systems
image plants but do not control the environment, rarely include replicated environmental units,
and usually validate with correlations rather than agreement statistics (L32). Low-cost open
growth chambers exist (L28, L29) but are single units or a pair, with no automated phenotyping,
no formal chamber-effect trial (L04) and no public longitudinal dataset.

## 2. Lettuce image datasets and trait estimation

The reference public dataset is the 3rd Autonomous Greenhouse Challenge RGB-D lettuce set (L05):
roughly 400 top-view RGB-D images with destructive fresh/dry weight, height, diameter and leaf
area. It has driven a series of papers (L06, L07, L08) reporting R² of about 0.9 and fresh-weight
errors of 6-9 %. Three structural limits recur:

1. **Cross-sectional**: each plant is photographed once, at harvest. There is no per-plant
   time series, so growth-rate and early-warning models cannot be trained or tested.
2. **Single environment, no treatments**: no stress contrasts and no per-plant environmental
   history.
3. **Evaluation**: random image-level splits within one greenhouse and one season. Transfer to
   a new run/chamber/cultivar is untested, so reported accuracies are upper bounds (L30, L31).

## 3. Stress detection

Image-based detectors of *visible* symptoms (e.g. tipburn, L21) work, but visible symptoms are
late. Multimodal work exists, yet "multimodal" typically means RGB + depth (L06) or RGB + thermal
(L24), or separate phenotype/image pipelines (L23). The searches run for this review did not find
a hydroponic lettuce study that (a) fuses RGB image time series with environmental sensor time
series, (b) scores *earliness* (lead time relative to a defined reference such as visible-symptom
onset or a growth-rate deviation), and (c) evaluates with the experimental unit (chamber-run) held
out. Absence in a scoping search is not proof of absence; LIT-02 must confirm.

## 4. Growth models, hybrid models and digital twins

Van Henten's two-state lettuce model (L01, L02) remains the standard mechanistic baseline and is
reused in most lettuce control studies. Recent hybrid/physics-informed and digital-twin papers
(L25, L26, L27 and a 2026 Frontiers framework found in the search) are mostly simulation studies,
calibrated and "validated" on synthetic data or on a single small experiment. Resource-efficiency
analyses of plant factories are also largely model-based (L20). The consistent gap is
**experimental validation on independent runs**, with metered energy and measured biomass.

## 5. Lighting strategy and energy

Dose-response work puts efficient sole-source lettuce production near 200-250 µmol m⁻² s⁻¹ and a
DLI ceiling near 17 mol m⁻² d⁻¹ for tipburn-sensitive cultivars (L17, L18, L34). At equal DLI,
longer photoperiods at lower PPFD tend to raise light-use efficiency (L15, L17). Adaptive
lighting has been demonstrated physiologically (L14) and in greenhouses (L15); schedule
optimization against prices has been shown in simulation (L16). A crop-cycle, replicated,
sole-source test with **energy per unit dry mass** as the pre-specified endpoint is uncommon.

## 6. Experimental design in controlled environments

Chambers set to identical conditions can still differ (L04), and plants in one chamber are
subsamples, not replicates, for any chamber-level treatment (L03, L33; Crop Science CE
guidelines). Much CEA machine-learning work ignores this in both statistics and
train/test splitting.

## 7. The research gap (defensible statement)

> There is no openly documented, replicated-unit, low-cost platform that produces **longitudinal,
> per-plant, multimodal** (RGB image series + synchronized environmental series + destructive
> ground truth) lettuce data under **controlled stress contrasts**, with the experimental unit
> correctly identified, and no study that uses such data to test, with leakage-safe evaluation,
> (i) whether sensor+image fusion gives *earlier* stress detection than either modality, and
> (ii) whether a hybrid physics+ML crop/energy model out-predicts its components on *held-out
> runs* and can drive lighting control to lower measured energy per unit biomass.

What would falsify the gap claim: a public dataset with per-plant daily-or-better RGB series,
logged environment, ≥2 stress factors, ≥4 independent units, destructive ground truth. LIT-02
searches specifically for this.

What this project must not claim: that low-cost phenotyping, lettuce biomass regression, or
lettuce digital twins are new in themselves. They are not. The contribution is the combination of
valid replication, longitudinal multimodal data, pre-specified analysis, and physical validation.

## 8. Search strings for LIT-02

```
("lettuce" OR "Lactuca sativa") AND ("phenotyping" OR "image-based") AND ("time series" OR longitudinal OR "time-lapse") AND (dataset OR "open data")
("lettuce" OR "leafy green*") AND (stress OR tipburn OR "nutrient deficien*" OR heat) AND ("early detection" OR "pre-symptomatic") AND (multimodal OR fusion OR "sensor data")
("digital twin" OR "hybrid model" OR "physics-informed") AND (lettuce OR "plant factory" OR "vertical farm") AND (validation OR experiment*)
("adaptive lighting" OR "dynamic lighting" OR "model predictive control") AND lettuce AND (energy OR "light use efficiency") AND ("sole-source" OR "plant factory" OR "growth chamber")
("growth chamber" OR "controlled environment") AND ("open-source" OR "low-cost") AND (hardware OR platform) AND (replicat* OR "chamber effect")
```

Inclusion: peer-reviewed or archived preprint, 2012 onward (plus seminal models), crop is lettuce
or a rosette leafy green, reports data or a validated instrument. Screening log template:
`docs/research/screening_log_template.csv`.

## Sources located in this session's web searches

- Tovar et al. 2018: https://pmc.ncbi.nlm.nih.gov/articles/PMC5895192
- Kim & van Iersel 2023: https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2023.1155722/pdf
- Lin et al. 2022: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9458202/
- Gang et al. 2022: https://mdpi.com/1424-8220/22/15/5499
- Xu et al. 2023: https://mdpi.com/2073-4395/13/10/2617
- Hamidon & Ahamed 2022: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9571858/
- CFIHL dataset: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11428101/
- Multi-modal water-N stress framework: https://itc.ktu.lt/index.php/ITC/article/view/43803
- Van Henten 1994: https://ideas.repec.org/a/eee/agisys/v45y1994i1p55-72.html and thesis https://edepot.wur.nl/205106
- Porter et al. 2015: https://pmc.ncbi.nlm.nih.gov/articles/PMC4578792
- Crop Science controlled-environment guidelines: https://sciencesocieties.org/publications/journals/author-resources/cs-instructions/controlled-environment-research
- van Iersel et al. 2016 (news release): https://www.eurekalert.org/news-releases/846291
- Nam, van Iersel & Ferrarezi review: https://pmc.ncbi.nlm.nih.gov/articles/PMC11748110
- Lork et al. 2020: https://arxiv.org/abs/2008.01325
- Low-cost programmable chamber: https://arxiv.org/pdf/1910.02740
- Wright et al. 2023: https://ishs.org/ishs-article/1369_17/
- Both 2003 (Cornell lettuce research): https://www.haifa-group.com/sites/default/files/2024-03/AJBothTenYearsofHydroponicLettuceResearch2003.pdf
- Hybrid aeroponic lettuce model: https://doi.org/10.1038/s41598-025-02763-9
- Kharraz & Szabó 2025: https://doaj.org/article/277942028fa44dffadd9c7a1f4dd0949
- Bridgelux EB Gen 3 datasheet DS132: https://www.bridgelux.com/sites/default/files/resource_media/DS132%20Bridgelux%20EB%20Series%20Gen3%20Data%20Sheet%2020190617%20Rev%20A.pdf
