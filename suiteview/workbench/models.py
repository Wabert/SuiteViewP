"""
PinnedDataset model — an in-memory snapshot of query results that can be
joined with other pinned datasets in the Workbench canvas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import uuid

import pandas as pd


@dataclass
class ColumnDef:
    """Column metadata for a pinned dataset's signature."""
    name: str
    dtype: str = "object"        # pandas dtype string
    sample_values: list[str] = field(default_factory=list)  # up to 5 samples

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "sample_values": self.sample_values,
        }

    @staticmethod
    def from_dict(data: dict) -> ColumnDef:
        return ColumnDef(
            name=data["name"],
            dtype=data.get("dtype", "object"),
            sample_values=data.get("sample_values", []),
        )

    @staticmethod
    def from_dataframe(df: pd.DataFrame, max_samples: int = 5) -> list[ColumnDef]:
        """Extract ColumnDef list from a DataFrame."""
        cols: list[ColumnDef] = []
        for col in df.columns:
            samples = (
                df[col]
                .dropna()
                .head(max_samples)
                .astype(str)
                .tolist()
            )
            cols.append(ColumnDef(
                name=str(col),
                dtype=str(df[col].dtype),
                sample_values=samples,
            ))
        return cols


@dataclass
class PinnedDataset:
    """A snapshot of query results pinned for use in the Workbench."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    source_type: str = ""        # cyberlife | tai | dynamic_group | db_query | xdb_query | workbench
    source_label: str = ""       # human-readable origin, e.g. "Cyberlife CKPR"
    source_sql: str = ""
    columns: list[ColumnDef] = field(default_factory=list)
    row_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    parquet_path: str = ""       # relative to store dir

    # Runtime-only (not persisted) ------------------------------------------
    dataframe: Optional[pd.DataFrame] = field(default=None, repr=False)

    # ---- Serialisation ----------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "source_type": self.source_type,
            "source_label": self.source_label,
            "source_sql": self.source_sql,
            "columns": [c.to_dict() for c in self.columns],
            "row_count": self.row_count,
            "created_at": self.created_at.isoformat(),
            "parquet_path": self.parquet_path,
        }

    @staticmethod
    def from_dict(data: dict) -> PinnedDataset:
        return PinnedDataset(
            id=data["id"],
            name=data.get("name", ""),
            source_type=data.get("source_type", ""),
            source_label=data.get("source_label", ""),
            source_sql=data.get("source_sql", ""),
            columns=[ColumnDef.from_dict(c) for c in data.get("columns", [])],
            row_count=data.get("row_count", 0),
            created_at=datetime.fromisoformat(
                data.get("created_at", datetime.now().isoformat())
            ),
            parquet_path=data.get("parquet_path", ""),
        )

    # ---- Helpers ----------------------------------------------------------

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    @property
    def memory_mb(self) -> float:
        """Approximate in-memory size in MB (0 if not loaded)."""
        if self.dataframe is None:
            return 0.0
        return self.dataframe.memory_usage(deep=True).sum() / (1024 * 1024)

    @property
    def shape_label(self) -> str:
        """Compact 'rows × cols' label for the UI."""
        return f"{self.row_count:,} × {len(self.columns)}"

    def is_loaded(self) -> bool:
        return self.dataframe is not None

    @staticmethod
    def from_dataframe(
        df: pd.DataFrame,
        *,
        name: str,
        source_type: str,
        source_label: str,
        source_sql: str = "",
    ) -> PinnedDataset:
        """Create a PinnedDataset from a live DataFrame."""
        return PinnedDataset(
            name=name,
            source_type=source_type,
            source_label=source_label,
            source_sql=source_sql,
            columns=ColumnDef.from_dataframe(df),
            row_count=len(df),
            dataframe=df,
        )
