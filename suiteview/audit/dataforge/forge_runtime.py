"""
DataForge runtime — orchestration that ties the model, the Snapshot store and
the DuckDB engine together.

Responsibilities:
- Add a shared Query to a Forge as an editable-copy **Source**.
- **Re-sync** a Source's definition from its shared Query.
- **Refresh** a Source: pull data via a (pluggable) fetcher and write its
  Snapshot, updating the metadata.
- Compile a saved Forge (its config) into engine specs and run it over the
  cached Snapshots.

The actual data pull is injected as ``fetch_fn`` so the orchestration is fully
unit-testable without live DB2/SQL Server (minipc-safe). The default fetcher
(:func:`default_fetch`) performs the real ODBC pull and is verified on the work
laptop.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable

import pandas as pd

from suiteview.audit import query_object_store
from suiteview.audit.query_object import QueryObject

from . import dataforge_store
from .dataforge_model import DataForge, DataForgeSource, SourceSnapshot
from .forge_engine import FilterSpec, JoinSpec, OutputColumn, ForgeResult, run_forge

logger = logging.getLogger(__name__)

# A fetcher takes a QueryObject (the Source's editable definition) and returns
# its data as a DataFrame. Live DB access is hidden behind this seam.
FetchFn = Callable[[QueryObject], pd.DataFrame]


# ── Building Sources from shared Queries ─────────────────────────────────

def add_query_as_source(forge: DataForge, query_name: str,
                        alias: str = "") -> DataForgeSource:
    """Add a shared Query to ``forge`` as an editable-copy Source.

    Copies the Query's current definition into the Source. No data is pulled;
    the Snapshot starts empty (a Refresh is required to populate it).
    """
    obj = query_object_store.load_object(query_name)
    if obj is None:
        raise ValueError(f"Query not found: {query_name}")
    source = DataForgeSource(
        query_name=query_name,
        alias=alias or query_name,
        definition=obj.to_dict(),
        filters=[],
        snapshot=SourceSnapshot(),
        synced_at=datetime.now().isoformat(),
    )
    forge.sources.append(source)
    return source


def resync_source(source: DataForgeSource) -> bool:
    """Pull the latest *definition* from the shared Query into this Source.

    Returns True if the definition changed. Marks the Snapshot stale on change
    (the data was pulled under the old definition).
    """
    obj = query_object_store.load_object(source.query_name)
    if obj is None:
        raise ValueError(f"Shared Query no longer exists: {source.query_name}")
    new_def = obj.to_dict()
    changed = new_def != source.definition
    source.definition = new_def
    source.synced_at = datetime.now().isoformat()
    if changed:
        source.snapshot.stale = True
    return changed


def mark_source_stale(source: DataForgeSource) -> None:
    """Flag that the Source's data no longer reflects its definition/filters."""
    source.snapshot.stale = True


def set_source_filters(source: DataForgeSource,
                       filters: list[dict[str, Any]]) -> None:
    """Replace a Source's filters; marks the Snapshot stale if they changed."""
    if filters != source.filters:
        source.filters = list(filters)
        source.snapshot.stale = True


# ── Refresh (pull data → Snapshot) ───────────────────────────────────────

def refresh_source(forge_name: str, source: DataForgeSource,
                   fetch_fn: FetchFn | None = None) -> SourceSnapshot:
    """Re-pull a Source's data and write its parquet Snapshot.

    ``fetch_fn`` receives the Source's (Forge-local) definition as a
    QueryObject and returns a DataFrame. Defaults to the real ODBC fetcher.
    Updates and returns the Source's Snapshot metadata.
    """
    fetch = fetch_fn or default_fetch
    obj = QueryObject.from_dict(source.definition)
    df = fetch(obj)

    dataforge_store.save_source_snapshot(
        forge_name, source.effective_alias(), df)
    source.snapshot = SourceSnapshot(
        created_at=datetime.now().isoformat(),
        row_count=int(len(df)),
        columns=list(df.columns),
        stale=False,
    )
    return source.snapshot


def default_fetch(obj: QueryObject) -> pd.DataFrame:
    """Real data pull for a Source definition (verified on the work laptop).

    Mirrors the legacy DataForge source loader: ad-hoc sources come from their
    captured metadata; everything else runs its SQL over ODBC.
    """
    from suiteview.audit.query_object import OBJECT_KIND_ADHOC_SOURCE

    if obj.kind == OBJECT_KIND_ADHOC_SOURCE:
        from suiteview.audit.dataforge.dataforge_group import (
            dataframe_from_adhoc_metadata)
        metadata = (obj.sources[0].metadata if obj.sources else {}) or {}
        return dataframe_from_adhoc_metadata(
            obj.source_design, metadata, columns=obj.result_columns)

    from suiteview.audit.dynamic_query import execute_odbc_query
    columns, rows = execute_odbc_query(obj.dsn, obj.sql)
    return pd.DataFrame([list(r) for r in rows], columns=columns)


# ── Filter conversion ─────────────────────────────────────────────────────

def source_filter_specs(source: DataForgeSource) -> list[FilterSpec]:
    """Convert a Source's stored filter dicts into engine FilterSpecs."""
    alias = source.effective_alias()
    specs: list[FilterSpec] = []
    for f in source.filters:
        col = f.get("column") or f.get("key", "").split(".", 1)[-1]
        if not col:
            continue
        specs.append(FilterSpec(
            source=alias,
            column=col,
            mode=f.get("mode", "contains"),
            value=f.get("value", ""),
            lo=f.get("lo", ""),
            hi=f.get("hi", ""),
            items=tuple(f.get("items", [])),
        ))
    return specs


# ── Running a Forge over Snapshots ───────────────────────────────────────

def load_snapshots(forge: DataForge) -> dict[str, pd.DataFrame]:
    """Load every Source's Snapshot DataFrame, keyed by alias.

    Raises ValueError naming the Sources whose Snapshots are missing — the
    caller should prompt a Refresh rather than pulling live on open.
    """
    snapshots: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for s in forge.sources:
        alias = s.effective_alias()
        df = dataforge_store.load_source_snapshot(forge.name, alias)
        if df is None:
            missing.append(alias)
        else:
            snapshots[alias] = df
    if missing:
        raise ValueError(
            "No Snapshot for Source(s): " + ", ".join(missing)
            + ". Refresh them before running the Forge.")
    return snapshots


def joins_from_config(config: dict[str, Any]) -> list[JoinSpec]:
    """Build JoinSpecs from a Forge config's ``joins`` list.

    Accepts both the new explicit form (left_source/right_source/left_keys/
    right_keys/how) and the legacy merge-op form (left/right/left_on/right_on/
    how, single-key).
    """
    specs: list[JoinSpec] = []
    for j in config.get("joins", []):
        if "left_source" in j:
            specs.append(JoinSpec(
                left_source=j["left_source"],
                right_source=j["right_source"],
                left_keys=tuple(j.get("left_keys", [])),
                right_keys=tuple(j.get("right_keys", [])),
                how=j.get("how", "inner"),
            ))
        else:  # legacy single-key merge op
            specs.append(JoinSpec(
                left_source=j["left"],
                right_source=j["right"],
                left_keys=(j["left_on"],),
                right_keys=(j["right_on"],),
                how=j.get("how", "inner"),
            ))
    return specs


def outputs_from_config(config: dict[str, Any]) -> list[OutputColumn] | None:
    """Build OutputColumns from a Forge config's ``outputs`` list, or None."""
    raw = config.get("outputs")
    if not raw:
        return None
    return [
        OutputColumn(source=o["source"], column=o["column"],
                     alias=o.get("alias"))
        for o in raw
    ]


def run_saved_forge(forge: DataForge,
                    snapshots: dict[str, pd.DataFrame] | None = None
                    ) -> ForgeResult:
    """Run a saved Forge over its Snapshots and return the engine result.

    Source filters come from each Source; result-scope filters and joins/
    outputs come from the Forge config. Snapshots are loaded from disk unless
    supplied (handy for tests).
    """
    if snapshots is None:
        snapshots = load_snapshots(forge)

    filters: list[FilterSpec] = []
    for s in forge.sources:
        filters.extend(source_filter_specs(s))

    # Result-scope filters target output column names (see forge_engine).
    result_filters = [
        FilterSpec(
            source="",
            column=rf["column"],
            mode=rf.get("mode", "contains"),
            value=rf.get("value", ""),
            lo=rf.get("lo", ""),
            hi=rf.get("hi", ""),
            items=tuple(rf.get("items", [])),
        )
        for rf in forge.config.get("result_filters", [])
    ]

    return run_forge(
        snapshots,
        joins_from_config(forge.config),
        filters=filters,
        result_filters=result_filters,
        outputs=outputs_from_config(forge.config),
        limit=forge.config.get("limit"),
    )
