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
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import pandas as pd

from suiteview.audit import query_object_store
from suiteview.audit.query_object import QueryObject

from . import dataforge_store
from .dataforge_model import DataForge, DataForgeSource, SourceSnapshot
from .forge_engine import (
    AppendSpec, FilterSpec, JoinSpec, OutputColumn, ForgeResult,
    compile_forge_sql, run_forge, run_manual_sql,
)

logger = logging.getLogger(__name__)

# A fetcher takes a QueryObject (the Source's editable definition) and returns
# its data as a DataFrame. Live DB access is hidden behind this seam.
FetchFn = Callable[[QueryObject], pd.DataFrame]


# ── Building Sources from shared Queries ─────────────────────────────────

def add_object_as_source(forge: DataForge, obj: QueryObject,
                         alias: str = "") -> DataForgeSource:
    """Add a QueryObject to ``forge`` as an editable-copy Source.

    Copies the Query's current definition into the Source. No data is pulled;
    the Snapshot starts empty (a Refresh is required to populate it). Prefer
    this object-based form — names may be duplicated, ids are unambiguous.
    """
    source = DataForgeSource(
        query_name=obj.name,
        query_object_id=obj.id,
        alias=alias or obj.name,
        definition=obj.to_dict(),
        filters=[],
        snapshot=SourceSnapshot(),
        synced_at=datetime.now().isoformat(),
    )
    forge.sources.append(source)
    return source


def add_query_as_source(forge: DataForge, query_name: str,
                        alias: str = "") -> DataForgeSource:
    """Add a shared Query to ``forge`` as a Source, by name (compat seam)."""
    obj = query_object_store.load_object(query_name)
    if obj is None:
        raise ValueError(f"Query not found: {query_name}")
    return add_object_as_source(forge, obj, alias)


def resync_source(source: DataForgeSource) -> bool:
    """Pull the latest *definition* from the shared Query into this Source.

    Returns True if the definition changed. Marks the Snapshot stale on change
    (the data was pulled under the old definition).
    """
    obj = query_object_store.load_object_by_id(source.query_object_id)
    if obj is None:
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


def result_filter_specs(config: dict[str, Any]) -> list[FilterSpec]:
    """Convert a Forge config's result-scope filter dicts into FilterSpecs.

    Result filters target *output* column names (the engine ignores their
    ``source``); see forge_engine.compile_forge_sql.
    """
    return [
        FilterSpec(
            source="",
            column=rf["column"],
            mode=rf.get("mode", "contains"),
            value=rf.get("value", ""),
            lo=rf.get("lo", ""),
            hi=rf.get("hi", ""),
            items=tuple(rf.get("items", [])),
        )
        for rf in config.get("result_filters", [])
    ]


# ── Manual mode (config-driven) ──────────────────────────────────────────

def is_manual_mode(config: dict[str, Any] | None) -> bool:
    """Whether the Forge runs its hand-written SQL instead of the visual design."""
    return (config or {}).get("sql_mode", "") == "manual"


# ── Running a Forge over Snapshots ───────────────────────────────────────

def source_schemas(forge: DataForge,
                   snapshots: dict[str, pd.DataFrame] | None = None,
                   ) -> dict[str, list[str]]:
    """Best-known columns per Source alias, without requiring a data pull.

    Prefers live Snapshot data when supplied, then the Snapshot metadata
    recorded at the last Refresh, then the definition's result columns. A
    Source with none of those yields an empty list (its columns are unknown
    until a Refresh).
    """
    schemas: dict[str, list[str]] = {}
    for s in forge.sources:
        alias = s.effective_alias()
        if snapshots is not None and alias in snapshots:
            schemas[alias] = list(snapshots[alias].columns)
        elif s.snapshot.columns:
            schemas[alias] = list(s.snapshot.columns)
        else:
            schemas[alias] = list(s.definition.get("result_columns", []) or [])
    return schemas


def compile_saved_forge_sql(forge: DataForge,
                            snapshots: dict[str, pd.DataFrame] | None = None,
                            *, limit: int | None = None) -> str:
    """Compile a saved Forge's visual design into its DuckDB SQL (no execution).

    This is the Visual→Manual generator: physical table names default to the
    Source aliases, so the returned statement runs unchanged in Manual mode
    (and is what the SQL tab shows the user). Raises ForgeEngineError when
    the design can't compile (e.g. disconnected joins).
    """
    filters: list[FilterSpec] = []
    for s in forge.sources:
        filters.extend(source_filter_specs(s))
    sql, _ = compile_forge_sql(
        source_schemas(forge, snapshots),
        joins_from_config(forge.config),
        filters=filters,
        result_filters=result_filter_specs(forge.config),
        outputs=outputs_from_config(forge.config),
        appends=appends_from_config(forge.config),
        limit=limit if limit is not None else forge.config.get("limit"),
    )
    return sql


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


def appends_from_config(config: dict[str, Any]) -> list[AppendSpec]:
    """Build AppendSpecs from a Forge config's ``appends`` list.

    Shape: ``[{"alias": "All Claims", "members": ["Claims A", "Claims B"]}]``.
    """
    return [
        AppendSpec(alias=a["alias"], members=tuple(a.get("members", [])))
        for a in config.get("appends", [])
    ]


def outputs_from_config(config: dict[str, Any]) -> list[OutputColumn] | None:
    """Build OutputColumns from a Forge config's ``outputs`` list, or None.

    Each output may carry an ``agg`` (``count``/``sum``/``min``/``max``/``avg``,
    or ``group``/blank for a plain grouping column) — the Display tab's
    aggregate toggle. ``aggregate`` is accepted as a synonym.
    """
    raw = config.get("outputs")
    if not raw:
        return None
    return [
        OutputColumn(source=o["source"], column=o["column"],
                     alias=o.get("alias"),
                     agg=o.get("agg", o.get("aggregate")))
        for o in raw
    ]


def run_saved_forge(forge: DataForge,
                    snapshots: dict[str, pd.DataFrame] | None = None,
                    *, limit: int | None = None,
                    ) -> ForgeResult:
    """Run a saved Forge over its Snapshots and return the engine result.

    In Manual mode (``config["sql_mode"] == "manual"``) the Forge's
    hand-written ``manual_sql`` runs directly against the Snapshot tables and
    the visual design (joins/filters/outputs) is ignored. Otherwise, Source
    filters come from each Source; result-scope filters and joins/outputs
    come from the Forge config. Snapshots are loaded from disk unless
    supplied (handy for tests). An explicit ``limit`` overrides the Forge's
    configured row cap — used for a fast preview (see ``preview_saved_forge``).
    """
    if snapshots is None:
        snapshots = load_snapshots(forge)

    effective_limit = limit if limit is not None else forge.config.get("limit")

    if is_manual_mode(forge.config):
        return run_manual_sql(
            snapshots, forge.config.get("manual_sql", ""),
            limit=effective_limit)

    filters: list[FilterSpec] = []
    for s in forge.sources:
        filters.extend(source_filter_specs(s))

    return run_forge(
        snapshots,
        joins_from_config(forge.config),
        filters=filters,
        result_filters=result_filter_specs(forge.config),
        outputs=outputs_from_config(forge.config),
        appends=appends_from_config(forge.config),
        limit=effective_limit,
    )


# ── Pre-flight validation ────────────────────────────────────────────────

@dataclass(frozen=True)
class ForgeIssue:
    """A pre-flight validation finding with actionable guidance.

    ``severity`` is "error" (blocks a run) or "warning" (run allowed).
    ``message`` says what is wrong; ``hint`` says where to fix it — the
    "→ go do X" guidance the app surfaces, in SuiteView's teaching style.
    """
    severity: str
    message: str
    hint: str = ""

    @property
    def is_error(self) -> bool:
        return self.severity == "error"

    @property
    def text(self) -> str:
        return f"{self.message}  → {self.hint}" if self.hint else self.message


def validate_forge(forge: DataForge) -> list[ForgeIssue]:
    """Pre-flight a Forge and return actionable issues (errors + warnings).

    Pure and snapshot-free: catches the structural problems that would
    otherwise surface as a raw engine error or a silently-wrong result —
    missing Snapshots, duplicate handles, malformed/unknown joins, and
    disconnected Sources — phrasing each as "what's wrong → where to fix it".
    Callers should block a run when any issue ``is_error``.

    In Manual mode the join checks are skipped (the hand-written SQL defines
    its own relationships); an empty SQL editor is an error instead.
    """
    sources = forge.sources
    if not sources:
        return [ForgeIssue("error", "This Forge has no Sources yet.",
                           "Click 'Queries' and add at least one Source.")]

    issues: list[ForgeIssue] = []
    aliases = [s.effective_alias() for s in sources]

    # Duplicate handles make joins/outputs ambiguous.
    for a in sorted({x for x in aliases if aliases.count(x) > 1}):
        issues.append(ForgeIssue(
            "error", f"Two Sources share the handle '{a}'.",
            "Give each Source a unique alias."))

    # Each Source needs data (a Snapshot) before the Forge can run.
    for s in sources:
        a = s.effective_alias()
        if not s.snapshot.exists:
            issues.append(ForgeIssue(
                "error", f"Source '{a}' has no data yet.",
                f"Right-click '{a}' and Refresh to pull its data."))
        elif s.snapshot.stale:
            issues.append(ForgeIssue(
                "warning", f"Source '{a}' has unapplied filter changes.",
                "Refresh it to apply them before running."))

    # Manual mode: the SQL replaces the visual joins entirely — skip the
    # join checks, but an empty editor can't run anything.
    if is_manual_mode(forge.config):
        if not str(forge.config.get("manual_sql", "")).strip():
            issues.append(ForgeIssue(
                "error", "Manual mode is on but the SQL editor is empty.",
                "Type SQL in the SQL tab, or switch Manual mode off."))
        return issues

    # Append Tables: members are represented by their append alias in the
    # join graph (the append consumes them — design §9).
    member_to_append: dict[str, str] = {}
    append_aliases: list[str] = []
    try:
        for ap in appends_from_config(forge.config):
            append_aliases.append(ap.alias)
            for m in ap.members:
                member_to_append[m] = ap.alias
    except Exception as exc:
        issues.append(ForgeIssue(
            "error", f"An Append Table is malformed: {exc}",
            "Re-create the Append Table on the Joins canvas."))

    # Joins: parse, check endpoints, check connectivity.
    alias_set = set(aliases) | set(append_aliases)
    try:
        specs = joins_from_config(forge.config)
    except Exception as exc:  # malformed join (e.g. mismatched key counts)
        issues.append(ForgeIssue(
            "error", f"A join is malformed: {exc}",
            "Re-draw the join so each side has matching keys."))
        specs = []

    valid_edges: list[tuple[str, str]] = []
    for spec in specs:
        missing = [s for s in (spec.left_source, spec.right_source)
                   if s not in alias_set]
        if missing:
            issues.append(ForgeIssue(
                "error",
                f"A join references {', '.join(repr(m) for m in missing)}, "
                f"which is not a Source here.",
                "Remove that join or add the missing Source."))
        else:
            valid_edges.append((spec.left_source, spec.right_source))

    # Connectivity: every surviving node (Sources not consumed by an append,
    # plus the Append Tables) must connect to the first.
    nodes = [a for a in aliases if a not in member_to_append] + append_aliases
    if len(nodes) > 1:
        adj: dict[str, set[str]] = {a: set() for a in nodes}
        for left, right in valid_edges:
            left = member_to_append.get(left, left)
            right = member_to_append.get(right, right)
            if left in adj and right in adj:
                adj[left].add(right)
                adj[right].add(left)
        seen: set[str] = set()
        stack = [nodes[0]]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(adj[cur] - seen)
        unreached = [a for a in nodes if a not in seen]
        if unreached:
            issues.append(ForgeIssue(
                "error",
                f"These Sources aren't joined to the rest: "
                f"{', '.join(unreached)}.",
                "Draw a join line to connect them, or remove unused Sources."))

    return issues


def preview_saved_forge(forge: DataForge,
                        snapshots: dict[str, pd.DataFrame] | None = None,
                        limit: int = 100) -> ForgeResult:
    """Run a Forge with a row cap for a fast preview over Snapshots."""
    return run_saved_forge(forge, snapshots, limit=limit)
