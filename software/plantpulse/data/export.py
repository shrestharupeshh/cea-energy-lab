"""Reproducible dataset export (Frictionless-style data package with checksums).

`export_dataset` writes a self-contained, versioned bundle ready for deposition (Zenodo / Dryad /
4TU.ResearchData): processed tables, metadata tables as CSV, a manifest with SHA-256 for every
file, datapackage.json, README and LICENSE. The treatment allocation is included in a separate
file so that blinded analyses can be reproduced.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .store import sha256_file
from .validation import CHECKS, QC_NAMES

META_TABLES = ["experiment", "treatment", "unit", "plant", "sensor", "calibration", "camera", "image", "image_plant",
               "manual_measurement", "intervention", "setpoint_log"]
LICENSE_TEXT = "Data: Creative Commons Attribution 4.0 International (CC BY 4.0)\nhttps://creativecommons.org/licenses/by/4.0/\n"


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def export_dataset(db, store, experiments: list[str], out_dir: str | Path, version: str, include_images: bool = True,
                   title: str = "PLANTPULSE longitudinal multimodal lettuce dataset") -> Path:
    out = Path(out_dir) / f"plantpulse-dataset-{version}"
    if out.exists():
        raise FileExistsError(f"{out} exists: dataset versions are immutable, choose a new version")
    (out / "metadata").mkdir(parents=True)
    classes = set(db.q(f"SELECT data_class FROM experiment WHERE experiment_id IN ({','.join('?' * len(experiments))})", experiments)["data_class"])
    resources = []
    ph = ",".join("?" * len(experiments))
    for table in META_TABLES:
        cols = [r[1] for r in db.con.execute(f"PRAGMA table_info({table})")]
        if "experiment_id" in cols:
            df = db.q(f"SELECT * FROM {table} WHERE experiment_id IN ({ph})", experiments)
        elif "unit_id" in cols:
            df = db.q(f"SELECT t.* FROM {table} t JOIN unit u USING (unit_id) WHERE u.experiment_id IN ({ph})", experiments)
        elif "plant_id" in cols:
            df = db.q(f"SELECT t.* FROM {table} t JOIN plant p USING (plant_id) JOIN unit u USING (unit_id) WHERE u.experiment_id IN ({ph})", experiments)
        elif "image_id" in cols:
            df = db.q(f"SELECT t.* FROM {table} t JOIN image i USING (image_id) WHERE i.experiment_id IN ({ph})", experiments)
        else:
            df = db.q(f"SELECT * FROM {table}")
        if table == "unit":                      # allocation is exported separately
            df.drop(columns=["treatment_id"]).to_csv(out / "metadata" / "unit.csv", index=False)
            df[["unit_id", "treatment_id"]].to_csv(out / "metadata" / "allocation_UNBLINDING.csv", index=False)
            continue
        df.to_csv(out / "metadata" / f"{table}.csv", index=False)
    for exp in experiments:
        src = store.processed / exp
        if src.exists():
            shutil.copytree(src, out / "processed" / exp)
        if include_images and (store.raw / exp / "images").exists():
            shutil.copytree(store.raw / exp / "images", out / "images" / exp)
    (out / "LICENSE").write_text(LICENSE_TEXT)
    (out / "metadata" / "qc_flags.json").write_text(json.dumps({"bits": {str(k): v for k, v in QC_NAMES.items()},
                                                                  "checks": {k: list(v) for k, v in CHECKS.items()}}, indent=1))
    warn = "" if classes <= {"experimental"} else (
        "\n**WARNING: this bundle contains data of class " + ", ".join(sorted(classes - {"experimental"})) +
        ". Simulated data are software test fixtures and pilot data are commissioning records; neither is an experimental result.**\n")
    (out / "README.md").write_text(f"""# {title} - version {version}
{warn}
Created {datetime.now(timezone.utc):%Y-%m-%d} by `plantpulse.data.export` at code commit `{_commit()}`.
Experiments: {', '.join(experiments)} (data classes: {', '.join(sorted(classes))}).

## Contents
- `metadata/*.csv` - experiment, treatment, unit, plant, sensor, calibration, camera, image, manual measurement,
  intervention and setpoint tables. `allocation_UNBLINDING.csv` maps units to treatments.
- `processed/<experiment>/sensors_1min.parquet` - calibrated 1-minute environment records with `_qc` bit flags
  (`metadata/qc_flags.json`), `traits.parquet` - image-derived traits per plant and time.
- `images/` - top-view RGB images, named `<experiment>-P<pod>-S<station>-<UTC>.png`.
- `manifest.csv` - SHA-256 of every file. `datapackage.json` - machine-readable description.

## Identifiers
Plant `EXP-YYYY-CODE-Pnn-Nnn`; unit (pod-run) `EXP-YYYY-CODE-Pnn`; all timestamps UTC (ISO 8601).
The experimental unit for chamber-level treatments is the unit (pod-run), not the plant.

## Metadata standard
Fields map to MIAPPE 1.1 (investigation = study programme, study = experiment, observation unit = plant,
experimental factor = treatment, environment = daily summaries). See docs/architecture/data_architecture.md.

## License
CC BY 4.0. Cite the dataset DOI and the platform paper.
""")
    rows = []
    for f in sorted(p for p in out.rglob("*") if p.is_file()):
        rows.append({"path": str(f.relative_to(out)), "bytes": f.stat().st_size, "sha256": sha256_file(f)})
        if f.suffix in (".csv", ".parquet"):
            resources.append({"name": f.stem.lower().replace("_", "-"), "path": str(f.relative_to(out)), "format": f.suffix[1:]})
    manifest = pd.DataFrame(rows)
    manifest.to_csv(out / "manifest.csv", index=False)
    msha = sha256_file(out / "manifest.csv")
    (out / "datapackage.json").write_text(json.dumps({
        "name": f"plantpulse-dataset-{version}", "title": title, "version": version, "created": datetime.now(timezone.utc).isoformat(),
        "licenses": [{"name": "CC-BY-4.0", "path": "https://creativecommons.org/licenses/by/4.0/"}],
        "data_classes": sorted(classes), "experiments": experiments, "manifest_sha256": msha, "resources": resources}, indent=1))
    db.x("INSERT OR REPLACE INTO dataset_version (version, created_utc, experiments, manifest_sha256, code_commit, license) VALUES (?,?,?,?,?,?)",
         (version, datetime.now(timezone.utc).isoformat(), ",".join(experiments), msha, _commit(), "CC-BY-4.0"))
    return out


def verify_dataset(path: str | Path) -> list[str]:
    """Re-hash every file against the manifest; returns the list of problems (empty = intact)."""
    path = Path(path)
    man = pd.read_csv(path / "manifest.csv")
    problems = []
    for _, r in man.iterrows():
        f = path / r["path"]
        if not f.exists():
            problems.append(f"missing {r['path']}")
        elif sha256_file(f) != r["sha256"]:
            problems.append(f"checksum mismatch {r['path']}")
    return problems
