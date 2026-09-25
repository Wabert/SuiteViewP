"""
Mixed-source Visual Queries — database tables joined with File Source datasets.

A Visual Query may combine ODBC tables (DB2 / SQL Server) with member tables of
saved File Sources. No single engine can see both, so the query is federated:

1. Every file table used by the query is loaded (``file_query_runner``).
2. Each database table is *staged* with its own read-only SELECT on its DSN.
   The query's filters on that table are pushed down, and — when a join makes
   it safe — the table is also restricted to the key values already present in
   a staged neighbour (``KEY IN (...)``, chunked). A policy list in a CSV thus
   pulls only those policies from DB2, never the whole table.
3. The same Visual Query design is compiled to the DuckDB dialect and run once
   over all the staged DataFrames.

Correctness rules (a quietly-wrong join is worse than an error):

* Key pushdown is only used where rows it removes could never reach the result:
  an INNER join, or the null-supplying side of a LEFT/RIGHT join. A preserved
  side (or a FULL join) is never restricted by its partner.
* A database table's filters run on the database with its native semantics; the
  DuckDB statement keeps only ``column IS NOT NULL`` for them, which is exactly
  equivalent for the staged rows (and still removes null-supplied rows, as the
  original WHERE would).
* Keys joined across sources are compared on one basis: numerically when either
  side is a database numeric column, otherwise as trimmed text. File key columns
  are re-read as text first so identifiers keep their leading zeros.
* A database table with neither a filter nor a safe key restriction would be
  downloaded in full; :meth:`FederatedPlan.unrestricted_tables` reports it so the
  UI can ask before running.

Pure planning/execution logic — no Qt. ODBC and file access are injectable so the
behaviour is unit-testable without a database.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Callable

from suiteview.audit.dynamic_query import (
    DUCKDB,
    _q,
    _q_table,
    build_dynamic_sql,
    build_join_sql,
    filter_conditions,
    order_join_infos,
    split_field_key,
)
from suiteview.audit.query_sources import is_list_token, is_local_token

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)

PUSHDOWN_CHUNK_SIZE = 1000
# Hidden join-key columns added to staged frames; dropped from the result.
KEY_HELPER_PREFIX = "__svk"

_NUMERIC_TYPE_WORDS = (
    "DECIMAL", "NUMERIC", "INT", "FLOAT", "DOUBLE", "REAL", "DECFLOAT", "MONEY",
    "NUMBER",
)


class FederatedQueryError(RuntimeError):
    """Raised when a mixed-source query cannot be planned or executed."""


def is_numeric_type_name(type_name: str) -> bool:
    upper = str(type_name or "").upper()
    return any(word in upper for word in _NUMERIC_TYPE_WORDS)


# Keys that only narrow to a few broad groups (a company, the inforce system,
# a coverage phase) restrict far less than a policy identifier.
_BROAD_KEYS = frozenset({"CK_SYS_CD", "CK_CMP_CD", "COV_PHA_NBR"})


def _pushdown_rank(candidate: "PushdownCandidate") -> tuple[int, int]:
    from suiteview.audit.policy_list import COMPANY_ALIASES, SYSTEM_ALIASES, normalize_name

    broad = (candidate.column.upper() in _BROAD_KEYS
             or normalize_name(candidate.column) in COMPANY_ALIASES | SYSTEM_ALIASES)
    return (1 if broad else 0, 0)


# ── Plan ──────────────────────────────────────────────────────────────────

@dataclass
class PushdownCandidate:
    """``table.column IN (values of from_table.from_column)`` is safe."""

    column: str
    from_table: str
    from_column: str


@dataclass
class StagingStep:
    """One database table fetched on its own DSN before the DuckDB join."""

    table: str
    dsn: str
    dialect: str
    columns: list[str] | None
    filters: list[dict] = field(default_factory=list)
    pushdowns: list[PushdownCandidate] = field(default_factory=list)

    @property
    def restricted(self) -> bool:
        return bool(self.filters or self.pushdowns)

    def conditions(self) -> list[str]:
        conds: list[str] = []
        for filt in self.filters:
            conds.extend(filter_conditions(filt, _q(filt["column"], self.dialect)))
        return conds

    def render(self, extra_condition: str = "") -> str:
        cols = "*"
        if self.columns:
            cols = ", ".join(_q(col, self.dialect) for col in self.columns)
        sql = f"SELECT {cols}\nFROM {_q_table(self.table, self.dialect)}"
        conds = self.conditions()
        if extra_condition:
            conds.append(extra_condition)
        if conds:
            sql += "\nWHERE " + "\n  AND ".join(conds)
        return sql


@dataclass
class FederatedPlan:
    primary: str
    table_sources: dict[str, str]
    # Tables SuiteView loads itself: File Source members and pasted lists.
    local_tables: list[str]
    steps: list[StagingStep]
    final_sql: str
    cross_key_pairs: list[tuple[str, str, str, str]]
    source_labels: dict[str, str] = field(default_factory=dict)
    # Pasted lists: table → {"columns": [...], "rows": [[...], ...]}.
    inline_tables: dict[str, dict] = field(default_factory=dict)
    # Cross-source keys: (table, column, helper, table, column, helper).
    key_helpers: list[tuple[str, str, str, str, str, str]] = field(default_factory=list)

    def unrestricted_tables(self) -> list[str]:
        return [step.table for step in self.steps if not step.restricted]

    def text_key_columns(self, table: str) -> list[str]:
        cols: list[str] = []
        for ta, ca, tb, cb in self.cross_key_pairs:
            for t, c in ((ta, ca), (tb, cb)):
                if t == table and c not in cols:
                    cols.append(c)
        return cols

    def _local_line(self, table: str) -> str:
        if table in self.inline_tables:
            count = len(self.inline_tables[table].get("rows", []))
            return f"-- [pasted list] {table}  ({count} rows)"
        label = self.source_labels.get(self.table_sources.get(table, ""), "")
        return f"-- [file] {table}" + (f"  ({label})" if label else "")

    def describe(self) -> str:
        """SQL-tab text: the staging plan as comments, then the DuckDB statement."""
        if not self.steps:
            lines = ["-- File datasets / pasted lists are loaded and queried in DuckDB."]
            lines.extend(self._local_line(table) for table in self.local_tables)
            return "\n".join([*lines, "", self.final_sql])
        lines = [
            "-- Mixed-source query: each database table is fetched on its own",
            "-- connection, then everything is joined with the file datasets /",
            "-- pasted lists in DuckDB by the statement at the end.",
        ]
        for table in self.local_tables:
            lines.append("--")
            lines.append(self._local_line(table))
        for index, step in enumerate(self.steps, start=1):
            lines.append("--")
            lines.append(f"-- [{index}] {step.table}  ({step.dsn})")
            extra = ""
            if step.pushdowns:
                choices = " or ".join(
                    f"{p.from_table}.{p.from_column}" for p in step.pushdowns)
                lines.append(
                    f"--     restricted to {step.pushdowns[0].column} values found in {choices}")
                extra = f"{_q(step.pushdowns[0].column, step.dialect)} IN (<key values>)"
            elif not step.filters:
                lines.append("--     NOT RESTRICTED: the whole table is downloaded")
            for sql_line in step.render(extra).splitlines():
                lines.append(f"--   {sql_line}")
        if self.key_helpers:
            lines.append("--")
            lines.append(f"-- {KEY_HELPER_PREFIX}… columns are normalized copies of the join "
                         "keys (text or number),")
            lines.append("-- so database and file/list keys compare alike; they are not shown.")
        lines.append("")
        lines.append(self.final_sql)
        return "\n".join(lines)


def plan_federated_query(
    *,
    table_sources: dict[str, str],
    used_tables: list[str],
    primary_table: str,
    field_filters: list[dict],
    select_columns: list[dict],
    join_infos: list[dict],
    max_count: str,
    display_all: bool = False,
    distinct: bool = False,
    cte_prefix: str = "",
    dialect_for: Callable[[str], str] | None = None,
    source_labels: dict[str, str] | None = None,
    inline_tables: dict[str, dict] | None = None,
) -> FederatedPlan:
    """Plan a query whose tables live in more than one engine.

    ``table_sources`` maps each table to its source: an ODBC DSN, a
    ``file:<id>`` File Source token or a ``list:<table>`` pasted list (whose data
    is in ``inline_tables``). ``used_tables`` are the tables referenced by fields
    and joins (a CTE Common Table has no source and is ignored).
    """
    from suiteview.core.odbc_utils import detect_dialect

    dialect_for = dialect_for or detect_dialect
    known = [t for t in table_sources if t]
    tables = [t for t in used_tables if t in table_sources]
    ordered = order_join_infos(primary_table, join_infos) if join_infos else []
    inline_tables = dict(inline_tables or {})
    for table in tables:
        if is_list_token(table_sources[table]) and table not in inline_tables:
            raise FederatedQueryError(
                f"The pasted list {table!r} has no data. Remove it and paste it again.")

    def table_of(spec: dict) -> str:
        return split_field_key(spec.get("field_key", ""), known)[0]

    file_tables = [t for t in tables if is_local_token(table_sources[t])]
    odbc_tables = [t for t in tables if not is_local_token(table_sources[t])]

    # Columns each database table must return.
    needs_all = display_all or not select_columns or any(
        ji.get("extra_conditions") for ji in join_infos)
    needed: dict[str, list[str]] = {t: [] for t in odbc_tables}

    def need(table: str, column: str):
        if table in needed and column and column not in needed[table]:
            needed[table].append(column)

    for spec in [*select_columns, *field_filters]:
        need(table_of(spec), spec["column"])
    cross_pairs: list[tuple[str, str, str, str]] = []
    # (restricted table, its column, source table, source column, safe)
    edges: list[tuple[str, str, str, str, bool]] = []
    for ji in ordered:
        lt, rt = ji["left_table"], ji["right_table"]
        how = str(ji.get("join_type", "")).upper()
        push_right = how.startswith("INNER") or how.startswith("LEFT")
        push_left = how.startswith("INNER") or how.startswith("RIGHT")
        pairs = [(lt, lc, rt, rc) for lc, rc in ji.get("on_pairs", [])]
        pairs.extend(ji.get("cross_pairs", []))
        for ta, ca, tb, cb in pairs:
            need(ta, ca)
            need(tb, cb)
            if table_sources.get(ta) != table_sources.get(tb):
                cross_pairs.append((ta, ca, tb, cb))
        for lc, rc in ji.get("on_pairs", []):
            edges.append((rt, rc, lt, lc, push_right))
            edges.append((lt, lc, rt, rc, push_left))

    filters_by_table: dict[str, list[dict]] = {t: [] for t in odbc_tables}
    for filt in field_filters:
        table = table_of(filt)
        if table in filters_by_table:
            filters_by_table[table].append(filt)

    # Stage file tables first, then each database table as soon as a staged
    # neighbour can restrict it; otherwise prefer filtered tables.
    staged = set(file_tables)

    def candidates(table: str) -> list[PushdownCandidate]:
        return [
            PushdownCandidate(column=col, from_table=src, from_column=src_col)
            for tgt, col, src, src_col, ok in edges
            if ok and tgt == table and src in staged
        ]

    remaining = list(odbc_tables)
    steps: list[StagingStep] = []
    while remaining:
        pick = next((t for t in remaining if candidates(t)), None)
        if pick is None:
            pick = next((t for t in remaining if filters_by_table[t]), remaining[0])
        dsn = table_sources[pick]
        steps.append(StagingStep(
            table=pick,
            dsn=dsn,
            dialect=dialect_for(dsn),
            columns=None if needs_all else list(needed[pick]),
            filters=list(filters_by_table[pick]),
            pushdowns=sorted(candidates(pick), key=_pushdown_rank),
        ))
        staged.add(pick)
        remaining.remove(pick)

    # DuckDB statement: database filters already ran on the database.
    odbc_set = set(odbc_tables)
    final_filters = [
        {**filt, "mode": "not_null"} if table_of(filt) in odbc_set else filt
        for filt in field_filters
    ]
    # Cross-source keys are compared through hidden helper columns holding the
    # normalized value, so the user's own columns are shown exactly as loaded.
    key_helpers: list[tuple[str, str, str, str, str, str]] = []
    final_joins: list[dict] = []
    for index, ji in enumerate(join_infos):
        lt, rt = ji["left_table"], ji["right_table"]
        pairs = []
        for pos, (lc, rc) in enumerate(ji.get("on_pairs", [])):
            if table_sources.get(lt) != table_sources.get(rt):
                lh, rh = f"{KEY_HELPER_PREFIX}{index}_{pos}_l", f"{KEY_HELPER_PREFIX}{index}_{pos}_r"
                key_helpers.append((lt, lc, lh, rt, rc, rh))
                pairs.append((lh, rh))
            else:
                pairs.append((lc, rc))
        final_joins.append({**ji, "on_pairs": pairs})
    if join_infos:
        final_sql = build_join_sql(
            primary_table, max_count, final_filters,
            join_infos=final_joins, select_columns=select_columns,
            display_all=display_all, distinct=distinct, dialect=DUCKDB)
    else:
        final_sql = build_dynamic_sql(
            primary_table, max_count, final_filters,
            select_columns=select_columns, display_all=display_all,
            distinct=distinct, dialect=DUCKDB)
    if cte_prefix:
        final_sql = cte_prefix + "\n" + final_sql

    return FederatedPlan(
        primary=primary_table,
        table_sources={t: table_sources[t] for t in tables},
        local_tables=file_tables,
        steps=steps,
        final_sql=final_sql,
        cross_key_pairs=cross_pairs,
        source_labels=dict(source_labels or {}),
        inline_tables={t: inline_tables[t] for t in file_tables if t in inline_tables},
        key_helpers=key_helpers,
    )


# ── Execution ─────────────────────────────────────────────────────────────

class OdbcSession:
    """One read-only connection per DSN for the life of a federated run."""

    def __init__(self):
        self._connections: dict[str, object] = {}

    def _connection(self, dsn: str):
        conn = self._connections.get(dsn)
        if conn is None:
            import pyodbc

            conn = pyodbc.connect(f"DSN={dsn}", autocommit=True)
            self._connections[dsn] = conn
        return conn

    def fetch(self, dsn: str, sql: str) -> "pd.DataFrame":
        import pandas as pd

        cursor = self._connection(dsn).cursor()
        try:
            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
        finally:
            cursor.close()
        return pd.DataFrame([list(r) for r in rows], columns=columns)

    def column_types(self, dsn: str, table: str) -> dict[str, str]:
        from suiteview.audit.dialogs.tables_dialog import _clean_odbc_identifier

        parts = [_clean_odbc_identifier(part) for part in table.split(".", 1)]
        schema, name = (parts[0], parts[1]) if len(parts) == 2 else (None, parts[0])
        cursor = self._connection(dsn).cursor()
        try:
            return {
                str(_clean_odbc_identifier(row.column_name)).upper():
                    str(_clean_odbc_identifier(row.type_name))
                for row in cursor.columns(table=name, schema=schema)
            }
        except Exception:
            logger.debug("Column metadata unavailable for %s on %s", table, dsn,
                         exc_info=True)
            return {}
        finally:
            cursor.close()

    def close(self):
        for conn in self._connections.values():
            try:
                conn.close()
            except Exception:
                logger.debug("Closing federated ODBC connection failed", exc_info=True)
        self._connections.clear()


def load_file_table(token: str, table: str,
                    text_columns: list[str] | None = None) -> "pd.DataFrame":
    """Load one File Source member table; ``text_columns`` keep their raw text."""
    from suiteview.audit import file_query_runner
    from suiteview.audit.query_sources import resolve_file_token

    fds = resolve_file_token(token)
    if fds is None:
        raise FederatedQueryError(
            f"The file dataset for {table!r} could not be found. It may have been "
            "deleted from Objects > File Sources.")
    tables = file_query_runner.load_source_tables(fds, [table])
    if table not in tables:
        raise FederatedQueryError(
            f"{table!r} is no longer a member of File Source {fds.name!r}.")
    df = tables[table]
    wanted = [c for c in (text_columns or []) if c in df.columns]
    if wanted:
        text = file_query_runner.load_source_tables(fds, [table], dtype=str)[table]
        for col in wanted:
            df[col] = text[col]
    return df


def inline_dataframe(data: dict) -> "pd.DataFrame":
    """A pasted list as text columns (values stay exactly as normalized)."""
    import pandas as pd

    columns = list(data.get("columns", []))
    rows = [list(row)[:len(columns)] + [""] * (len(columns) - len(row))
            for row in data.get("rows", [])]
    return pd.DataFrame(rows, columns=columns, dtype=object)


def _is_number(value) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def _is_missing(value) -> bool:
    import pandas as pd

    return value is None or (not isinstance(value, str) and bool(pd.isna(value)))


def _series_is_numeric(series) -> bool:
    import pandas as pd

    if pd.api.types.is_bool_dtype(series.dtype):
        return False
    if pd.api.types.is_numeric_dtype(series.dtype):
        return True
    values = series.dropna()
    return bool(len(values)) and all(_is_number(v) for v in values)


def _as_text(value) -> str | None:
    if _is_missing(value):
        return None
    if _is_number(value):
        number = Decimal(str(value))
        if number == number.to_integral_value():
            return str(int(number))
        return format(number.normalize(), "f")
    text = str(value).strip()
    return text or None


def _as_number(value):
    if _is_missing(value):
        return None
    if _is_number(value):
        return float(value)
    try:
        return float(Decimal(str(value).strip()))
    except (InvalidOperation, ValueError):
        return None


def _pushdown_literals(values, numeric: bool) -> list[str]:
    literals: list[str] = []
    seen: set[str] = set()
    for value in values:
        if numeric:
            number = _as_number(value)
            if number is None:
                continue
            literal = str(int(number)) if float(number).is_integer() else repr(number)
        else:
            text = _as_text(value)
            if text is None:
                continue
            literal = "'" + text.replace("'", "''") + "'"
        if literal not in seen:
            seen.add(literal)
            literals.append(literal)
    return literals


def _find_column(df, column: str) -> str | None:
    if column in df.columns:
        return column
    upper = column.upper()
    return next((c for c in df.columns if str(c).upper() == upper), None)


def _normalize_cross_keys(frames: dict, plan: FederatedPlan,
                          odbc_numeric: dict[tuple[str, str], bool]) -> None:
    """Give every cross-source key pair one comparison basis (see module doc).

    The normalized values go into the plan's hidden helper columns; the user's
    columns are never changed.
    """
    def numeric(table, frame, col):
        if (table, col.upper()) in odbc_numeric:
            return odbc_numeric[(table, col.upper())]
        if is_local_token(plan.table_sources.get(table, "")):
            return False  # file and pasted keys are text
        return _series_is_numeric(frame[col])

    for ta, ca, ha, tb, cb, hb in plan.key_helpers:
        a, b = frames.get(ta), frames.get(tb)
        if a is None or b is None:
            raise FederatedQueryError(f"Join tables {ta} / {tb} were not loaded.")
        col_a, col_b = _find_column(a, ca), _find_column(b, cb)
        if col_a is None or col_b is None:
            missing = f"{ta}.{ca}" if col_a is None else f"{tb}.{cb}"
            raise FederatedQueryError(f"Join column {missing} was not found.")
        if numeric(ta, a, col_a) or numeric(tb, b, col_b):
            a[ha] = a[col_a].map(_as_number).astype("float64")
            b[hb] = b[col_b].map(_as_number).astype("float64")
        else:
            a[ha] = a[col_a].map(_as_text).astype(object)
            b[hb] = b[col_b].map(_as_text).astype(object)


def execute_federated_plan(
    plan: FederatedPlan,
    *,
    session: OdbcSession | None = None,
    file_loader: Callable[[str, str, list[str]], "pd.DataFrame"] | None = None,
    chunk_size: int = PUSHDOWN_CHUNK_SIZE,
) -> "pd.DataFrame":
    """Stage every table, then run the plan's DuckDB statement over them."""
    from suiteview.audit.dataforge import forge_engine
    from suiteview.core.sql_permissions import guard_query_sql

    own_session = session is None
    session = session or OdbcSession()
    file_loader = file_loader or load_file_table
    frames: dict = {}
    odbc_numeric: dict[tuple[str, str], bool] = {}
    try:
        for table in plan.local_tables:
            if table in plan.inline_tables:
                frames[table] = inline_dataframe(plan.inline_tables[table])
                continue
            frames[table] = file_loader(
                plan.table_sources[table], table, plan.text_key_columns(table))

        for step in plan.steps:
            types = session.column_types(step.dsn, step.table)
            for col, type_name in types.items():
                odbc_numeric[(step.table, col.upper())] = is_numeric_type_name(type_name)
            frames[step.table] = _stage(step, frames, types, session,
                                        chunk_size, guard_query_sql)

        _normalize_cross_keys(frames, plan, odbc_numeric)
        try:
            df = forge_engine.run_manual_sql(frames, plan.final_sql, limit=None).dataframe
        except forge_engine.ForgeEngineError as exc:
            raise FederatedQueryError(str(exc)) from exc
        helpers = [c for c in df.columns if str(c).startswith(KEY_HELPER_PREFIX)]
        return df.drop(columns=helpers) if helpers else df
    finally:
        if own_session:
            session.close()


def _stage(step: StagingStep, frames: dict, types: dict[str, str],
           session: OdbcSession, chunk_size: int, guard) -> "pd.DataFrame":
    import pandas as pd

    if not step.pushdowns:
        sql = step.render()
        guard(sql)
        return session.fetch(step.dsn, sql)

    # The most selective staged key (most distinct values) restricts best; on a
    # tie keep the planner's order, which puts identifiers before broad codes.
    def distinct_count(candidate: PushdownCandidate) -> int:
        frame = frames[candidate.from_table]
        col = _find_column(frame, candidate.from_column)
        return int(frame[col].nunique()) if col is not None else -1

    choice = max(enumerate(step.pushdowns),
                 key=lambda item: (distinct_count(item[1]), -item[0]))[1]
    source = frames[choice.from_table]
    source_col = _find_column(source, choice.from_column)
    if source_col is None:
        raise FederatedQueryError(
            f"Join column {choice.from_column!r} is not in {choice.from_table}.")
    type_name = types.get(choice.column.upper(), "")
    if type_name:
        numeric = is_numeric_type_name(type_name)
    else:
        numeric = _series_is_numeric(source[source_col])
    literals = _pushdown_literals(source[source_col].tolist(), numeric)
    qcol = _q(choice.column, step.dialect)
    if not literals:
        # No partner keys, so no rows can join; still fetch the column shape.
        sql = step.render("1 = 0")
        guard(sql)
        return session.fetch(step.dsn, sql)

    parts = []
    for start in range(0, len(literals), max(1, chunk_size)):
        chunk = literals[start:start + chunk_size]
        sql = step.render(f"{qcol} IN ({', '.join(chunk)})")
        if start == 0:
            # Chunks differ only in escaped literals; one permission check covers them.
            guard(sql)
        parts.append(session.fetch(step.dsn, sql))
    return pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0]
