"""Time-series storage: append-only raw Parquet, separate processed Parquet.

Layout under the data root (default experiments/):
  raw_data/<experiment>/sensors/pod=<NN>/date=<YYYY-MM-DD>/part-<n>.parquet     (never modified)
  raw_data/<experiment>/images/P<NN>/<YYYYMMDD>/<image_id>.png|.dng
  processed_data/<experiment>/sensors_1min.parquet, traits.parquet, features.parquet
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.raw = self.root / "raw_data"
        self.processed = self.root / "processed_data"

    # ------------------------------------------------------------ raw sensor frames
    def append_raw(self, experiment: str, pod: int, frames: pd.DataFrame) -> list[Path]:
        """Append frames (must contain utc as tz-aware datetime). One new immutable file per date."""
        if frames.empty:
            return []
        frames = frames.copy()
        frames["utc"] = pd.to_datetime(frames["utc"], utc=True)
        out = []
        for date, chunk in frames.groupby(frames["utc"].dt.strftime("%Y-%m-%d")):
            d = self.raw / experiment / "sensors" / f"pod={pod:02d}" / f"date={date}"
            d.mkdir(parents=True, exist_ok=True)
            n = len(list(d.glob("part-*.parquet")))
            path = d / f"part-{n:05d}.parquet"
            chunk.to_parquet(path, index=False)
            path.chmod(0o444)
            out.append(path)
        return out

    def read_raw(self, experiment: str, pod: int | None = None) -> pd.DataFrame:
        base = self.raw / experiment / "sensors"
        pattern = f"pod={pod:02d}/date=*/part-*.parquet" if pod else "pod=*/date=*/part-*.parquet"
        files = sorted(base.glob(pattern))
        if not files:
            return pd.DataFrame()
        parts = []
        for f in files:
            df = pd.read_parquet(f)
            if "pod" not in df:
                df["pod"] = int(f.parts[-3].split("=")[1])
            parts.append(df)
        return pd.concat(parts, ignore_index=True).sort_values(["pod", "utc"]).reset_index(drop=True)

    # ------------------------------------------------------------ processed tables
    def write_processed(self, experiment: str, name: str, df: pd.DataFrame) -> Path:
        d = self.processed / experiment
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{name}.parquet"
        df.to_parquet(path, index=False)
        return path

    def read_processed(self, experiment: str, name: str) -> pd.DataFrame:
        path = self.processed / experiment / f"{name}.parquet"
        return pd.read_parquet(path) if path.exists() else pd.DataFrame()

    def image_path(self, relpath: str) -> Path:
        return self.raw / relpath
