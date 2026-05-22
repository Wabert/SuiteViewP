"""
QueryObject model — the single named object users see for reusable queries.

This model intentionally wraps existing concepts instead of replacing them:
SavedQuery remains the editable designer snapshot, QDefinition remains an
executable SQL/schema definition, and Cyberlife can publish its generated SQL
as a specialized query object.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


OBJECT_KIND_VISUAL = "visual_query"
OBJECT_KIND_EXECUTABLE = "executable_query"
OBJECT_KIND_CYBERLIFE = "cyberlife_query"
OBJECT_KIND_MANUAL_SQL = "manual_sql"
OBJECT_KIND_ADHOC_SOURCE = "adhoc_source"

SOURCE_STATUS_REGISTERED = "registered"
SOURCE_STATUS_ADHOC = "adhoc"
SOURCE_STATUS_OBJECT = "query_object"


@dataclass
class QueryObjectSource:
    """One source used by a QueryObject."""

    name: str
    source_type: str = "table"
    dsn: str = ""
    status: str = SOURCE_STATUS_REGISTERED
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source_type": self.source_type,
            "dsn": self.dsn,
            "status": self.status,
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(data: dict) -> QueryObjectSource:
        return QueryObjectSource(
            name=data["name"],
            source_type=data.get("source_type", "table"),
            dsn=data.get("dsn", ""),
            status=data.get("status", SOURCE_STATUS_REGISTERED),
            metadata=data.get("metadata", {}),
        )


@dataclass
class QueryObjectField:
    """A stable result field exposed by a QueryObject."""

    name: str
    data_type: str = ""
    role: str = "output"  # output | input | join_key
    source: str = ""
    display_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "data_type": self.data_type,
            "role": self.role,
            "source": self.source,
            "display_name": self.display_name,
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(data: dict) -> QueryObjectField:
        return QueryObjectField(
            name=data["name"],
            data_type=data.get("data_type", ""),
            role=data.get("role", "output"),
            source=data.get("source", ""),
            display_name=data.get("display_name", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class QueryObject:
    """A named, reusable query/source object shown to users."""

    name: str
    kind: str = OBJECT_KIND_VISUAL
    description: str = ""
    tags: list[str] = field(default_factory=list)
    dsn: str = ""
    dialect: str = ""
    sql: str = ""
    sources: list[QueryObjectSource] = field(default_factory=list)
    fields: list[QueryObjectField] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    manual_layers: dict[str, str] = field(default_factory=dict)
    metadata_status: str = SOURCE_STATUS_REGISTERED
    source_design: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "tags": self.tags,
            "dsn": self.dsn,
            "dialect": self.dialect,
            "sql": self.sql,
            "sources": [s.to_dict() for s in self.sources],
            "fields": [f.to_dict() for f in self.fields],
            "config": self.config,
            "manual_layers": self.manual_layers,
            "metadata_status": self.metadata_status,
            "source_design": self.source_design,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @staticmethod
    def from_dict(data: dict) -> QueryObject:
        return QueryObject(
            name=data["name"],
            kind=data.get("kind", OBJECT_KIND_VISUAL),
            description=data.get("description", ""),
            tags=list(data.get("tags", [])),
            dsn=data.get("dsn", ""),
            dialect=data.get("dialect", ""),
            sql=data.get("sql", ""),
            sources=[QueryObjectSource.from_dict(s)
                     for s in data.get("sources", [])],
            fields=[QueryObjectField.from_dict(f)
                    for f in data.get("fields", [])],
            config=data.get("config", {}),
            manual_layers=data.get("manual_layers", {}),
            metadata_status=data.get("metadata_status", SOURCE_STATUS_REGISTERED),
            source_design=data.get("source_design", ""),
            created_at=datetime.fromisoformat(
                data.get("created_at", datetime.now().isoformat())
            ),
            updated_at=datetime.fromisoformat(
                data.get("updated_at", datetime.now().isoformat())
            ),
        )

    @property
    def result_columns(self) -> list[str]:
        return [f.name for f in self.fields if f.role in ("output", "join_key")]


def fields_from_columns(
    columns: list[str],
    column_types: dict[str, str] | None = None,
    *,
    source: str = "",
    join_keys: set[str] | None = None,
) -> list[QueryObjectField]:
    """Create QueryObjectField rows from result columns and optional types."""
    column_types = column_types or {}
    join_keys_norm = {c.lower() for c in (join_keys or set())}
    fields: list[QueryObjectField] = []
    for col in columns:
        role = "join_key" if col.lower() in join_keys_norm else "output"
        fields.append(QueryObjectField(
            name=col,
            data_type=column_types.get(col, ""),
            role=role,
            source=source,
            display_name=col,
        ))
    return fields


def _column_name_from_key(field_key: str) -> str:
    return field_key.rsplit(".", 1)[-1] if field_key else ""


def _saved_query_output_fields(saved_query) -> list[QueryObjectField]:
    column_types = saved_query.column_types or {}
    fields: list[QueryObjectField] = []
    seen: set[str] = set()

    for col in saved_query.result_columns or []:
        if col and col not in seen:
            fields.append(QueryObjectField(
                name=col,
                data_type=column_types.get(col, ""),
                role="output",
                source=saved_query.name,
                display_name=saved_query.display_names.get(col, col),
            ))
            seen.add(col)

    if fields:
        return fields

    select_tab = (saved_query.config or {}).get("select_tab", {})
    if select_tab.get("display_all", False):
        return []
    for item in select_tab.get("fields", []):
        field_key = item.get("field_key", "")
        col = _column_name_from_key(field_key)
        if col and col not in seen:
            fields.append(QueryObjectField(
                name=col,
                data_type=column_types.get(col, ""),
                role="output",
                source=field_key or saved_query.name,
                display_name=item.get("display_name") or saved_query.display_names.get(col, col),
                metadata={"aggregate": item.get("aggregate", 0), "field_key": field_key},
            ))
            seen.add(col)
    return fields


def _saved_query_input_fields(saved_query, existing: set[str]) -> list[QueryObjectField]:
    fields: list[QueryObjectField] = []
    for tab in (saved_query.config or {}).get("tabs", []):
        grid = tab.get("grid", {})
        for field_key, state in grid.get("fields", {}).items():
            col = _column_name_from_key(field_key)
            if not col or col in existing:
                continue
            fields.append(QueryObjectField(
                name=col,
                role="input",
                source=field_key,
                display_name=state.get("label_text") or saved_query.display_names.get(col, col),
                metadata={"field_key": field_key, "mode": state.get("mode")},
            ))
            existing.add(col)
    return fields


def _saved_query_join_fields(saved_query, existing: set[str]) -> list[QueryObjectField]:
    fields: list[QueryObjectField] = []
    joins_tab = (saved_query.config or {}).get("joins_tab", {})
    for card in joins_tab.get("cards", []):
        for condition in card.get("on_conditions", []):
            for side in ("left", "right"):
                col = condition.get(side, "")
                if not col or col in existing:
                    continue
                fields.append(QueryObjectField(
                    name=col,
                    role="join_key",
                    source=card.get(f"{side}_table", "") or card.get("left_table", ""),
                    display_name=saved_query.display_names.get(col, col),
                    metadata={"join_card": card.get("card_id", ""), "side": side},
                ))
                existing.add(col)
    return fields


def object_from_saved_query(saved_query) -> QueryObject:
    """Convert an existing SavedQuery into a QueryObject."""
    sources = [
        QueryObjectSource(
            name=table,
            source_type="table",
            dsn=saved_query.dsn,
            status=SOURCE_STATUS_REGISTERED,
        )
        for table in saved_query.tables
    ]
    fields = _saved_query_output_fields(saved_query)
    existing = {field.name for field in fields}
    fields.extend(_saved_query_input_fields(saved_query, existing))
    fields.extend(_saved_query_join_fields(saved_query, existing))
    now = datetime.now()
    return QueryObject(
        name=saved_query.name,
        kind=OBJECT_KIND_VISUAL,
        dsn=saved_query.dsn,
        sql=saved_query.sql,
        sources=sources,
        fields=fields,
        config=saved_query.config,
        source_design=saved_query.source_group,
        created_at=saved_query.created_at,
        updated_at=now,
    )


def object_from_qdefinition(qdefinition) -> QueryObject:
    """Convert an existing QDefinition into a QueryObject."""
    sources = [
        QueryObjectSource(
            name=table,
            source_type="table",
            dsn=qdefinition.dsn,
            status=SOURCE_STATUS_REGISTERED,
        )
        for table in qdefinition.tables
    ]
    fields = fields_from_columns(
        qdefinition.result_columns,
        qdefinition.column_types,
        source=qdefinition.name,
    )
    now = datetime.now()
    return QueryObject(
        name=qdefinition.name,
        kind=OBJECT_KIND_EXECUTABLE,
        dsn=qdefinition.dsn,
        sql=qdefinition.sql,
        sources=sources,
        fields=fields,
        source_design=qdefinition.source_design,
        created_at=qdefinition.created_at,
        updated_at=now,
    )


def qdefinition_from_query_object(query_object: QueryObject):
    """Adapt a QueryObject into the QDefinition shape used by DataForge.

    This keeps DataForge working while the broader UI migrates from separate
    SavedQuery/QDefinition concepts toward QueryObject sources.
    """
    from suiteview.audit.qdefinition import QDefinition

    qdefinition = QDefinition(
        name=query_object.name,
        forge_name="",
        sql=query_object.sql,
        dsn=query_object.dsn,
        source_design=query_object.source_design or query_object.kind,
        result_columns=query_object.result_columns,
        column_types={field.name: field.data_type for field in query_object.fields},
        tables=[source.name for source in query_object.sources],
        display_names={field.name: field.display_name for field in query_object.fields},
        created_at=query_object.created_at,
    )
    qdefinition.query_object_kind = query_object.kind
    qdefinition.query_object_config = query_object.config
    if query_object.sources:
        qdefinition.query_object_source_metadata = query_object.sources[0].metadata
    return qdefinition


def cyberlife_query_object(
    name: str,
    *,
    sql: str,
    dsn: str,
    region: str,
    system_code: str,
    criteria: dict[str, Any],
    result_columns: list[str] | None = None,
    column_types: dict[str, str] | None = None,
) -> QueryObject:
    """Create a QueryObject published by the specialized Cyberlife builder."""
    join_keys = {"policy_number", "policynumber", "tch_pol_id", "company", "ck_cmp_cd"}
    now = datetime.now()
    return QueryObject(
        name=name,
        kind=OBJECT_KIND_CYBERLIFE,
        dsn=dsn,
        dialect="DB2",
        sql=sql,
        sources=[QueryObjectSource(
            name="Cyberlife",
            source_type="specialized_builder",
            dsn=dsn,
            status=SOURCE_STATUS_OBJECT,
            metadata={"region": region, "system_code": system_code},
        )],
        fields=fields_from_columns(
            result_columns or [], column_types, source=name, join_keys=join_keys),
        config={"criteria": criteria, "region": region, "system_code": system_code},
        metadata_status=SOURCE_STATUS_OBJECT,
        source_design="Cyberlife",
        created_at=now,
        updated_at=now,
    )


def manual_sql_query_object(
    name: str,
    *,
    sql: str,
    dsn: str,
    result_columns: list[str],
    column_types: dict[str, str] | None = None,
) -> QueryObject:
    """Create a QueryObject from user-authored SQL and captured output schema."""
    now = datetime.now()
    return QueryObject(
        name=name,
        kind=OBJECT_KIND_MANUAL_SQL,
        dsn=dsn,
        sql=sql,
        sources=[QueryObjectSource(
            name="Manual SQL",
            source_type="manual_sql",
            dsn=dsn,
            status=SOURCE_STATUS_OBJECT,
        )],
        fields=fields_from_columns(result_columns, column_types, source=name),
        metadata_status=SOURCE_STATUS_OBJECT,
        source_design="Manual SQL",
        created_at=now,
        updated_at=now,
    )


def adhoc_source_object(
    name: str,
    *,
    source_type: str,
    metadata: dict[str, Any],
    columns: list[str],
    column_types: dict[str, str] | None = None,
) -> QueryObject:
    """Create a temporary/ad hoc source object that can later be promoted."""
    now = datetime.now()
    return QueryObject(
        name=name,
        kind=OBJECT_KIND_ADHOC_SOURCE,
        sources=[QueryObjectSource(
            name=name,
            source_type=source_type,
            status=SOURCE_STATUS_ADHOC,
            metadata=metadata,
        )],
        fields=fields_from_columns(columns, column_types, source=name),
        config={"source_metadata": metadata},
        metadata_status=SOURCE_STATUS_ADHOC,
        source_design=source_type,
        created_at=now,
        updated_at=now,
    )