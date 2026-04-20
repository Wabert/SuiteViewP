"""
Dataset store — persist and load PinnedDatasets.

Storage layout (under ~/.suiteview/workbench/):
    datasets/
        <uuid>.json        # metadata sidecar
        <uuid>.pkl         # row data (pickle)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from suiteview.workbench.models import PinnedDataset

logger = logging.getLogger(__name__)

_STORE_DIR = Path.home() / ".suiteview" / "workbench" / "datasets"


def _ensure_dir() -> Path:
    _STORE_DIR.mkdir(parents=True, exist_ok=True)
    return _STORE_DIR


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_datasets() -> list[PinnedDataset]:
    """Return all saved datasets (metadata only, DataFrame not loaded)."""
    _ensure_dir()
    datasets: list[PinnedDataset] = []
    for meta_file in sorted(_STORE_DIR.glob("*.json")):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            datasets.append(PinnedDataset.from_dict(data))
        except Exception:
            logger.exception("Failed to load dataset metadata: %s", meta_file)
    return datasets


def load_dataset(dataset_id: str) -> Optional[PinnedDataset]:
    """Load a single dataset's metadata (no DataFrame)."""
    meta_path = _STORE_DIR / f"{dataset_id}.json"
    if not meta_path.exists():
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return PinnedDataset.from_dict(json.load(f))
    except Exception:
        logger.exception("Failed to load dataset: %s", dataset_id)
        return None


def load_dataframe(ds: PinnedDataset) -> pd.DataFrame:
    """Load the pickled data into the dataset's .dataframe attribute.

    Returns the DataFrame (also sets ds.dataframe).
    """
    pkl_path = _STORE_DIR / ds.parquet_path
    if not pkl_path.exists():
        raise FileNotFoundError(f"Data file not found: {pkl_path}")
    df = pd.read_pickle(pkl_path)
    ds.dataframe = df
    return df


def save_dataset(ds: PinnedDataset) -> None:
    """Persist a PinnedDataset (metadata JSON + Parquet data).

    If ds.dataframe is not None it is written to Parquet and the
    parquet_path is updated.  If it *is* None only the metadata sidecar
    is (re-)written (e.g. after a rename).
    """
    _ensure_dir()

    # Write pickle if we have live data
    if ds.dataframe is not None:
        pkl_name = f"{ds.id}.pkl"
        pkl_path = _STORE_DIR / pkl_name
        ds.dataframe.to_pickle(pkl_path)
        ds.parquet_path = pkl_name

    # Write metadata sidecar
    meta_path = _STORE_DIR / f"{ds.id}.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(ds.to_dict(), f, indent=2)


def delete_dataset(dataset_id: str) -> None:
    """Remove a dataset's data and metadata files."""
    for suffix in (".json", ".pkl", ".parquet"):
        path = _STORE_DIR / f"{dataset_id}{suffix}"
        if path.exists():
            path.unlink()


def dataset_exists(dataset_id: str) -> bool:
    return (_STORE_DIR / f"{dataset_id}.json").exists()


def get_total_memory_mb() -> float:
    """Total Parquet file size on disk in MB (proxy for memory budget)."""
    _ensure_dir()
    total = sum(f.stat().st_size for f in _STORE_DIR.glob("*.pkl"))
    return total / (1024 * 1024)
