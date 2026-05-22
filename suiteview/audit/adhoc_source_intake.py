"""Ad hoc source intake for loose files used in audit/DataForge work."""
from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from suiteview.audit.query_object import (
    OBJECT_KIND_ADHOC_SOURCE,
    SOURCE_STATUS_REGISTERED,
    QueryObject,
    adhoc_source_object,
)


_SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xlsm", ".xls"}


def query_object_from_file(
    path: str | Path,
    *,
    name: str | None = None,
    sample_rows: int = 100,
    sheet_name: str | int | None = 0,
) -> QueryObject:
    """Infer a temporary QueryObject from a loose CSV or Excel file."""
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix not in _SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(_SUPPORTED_SUFFIXES))
        raise ValueError(f"Unsupported ad hoc source type: {suffix}. Supported: {supported}")

    if suffix == ".csv":
        columns, rows = _read_csv_sample(file_path, sample_rows)
        source_type = "csv"
        source_metadata: dict[str, Any] = {"path": str(file_path), "sample_rows": len(rows)}
    else:
        columns, rows = _read_excel_sample(file_path, sample_rows, sheet_name)
        source_type = "excel"
        source_metadata = {
            "path": str(file_path),
            "sheet_name": sheet_name,
            "sample_rows": len(rows),
        }

    object_name = name or file_path.stem
    column_types = {column: _infer_column_type([row.get(column, "") for row in rows])
                    for column in columns}
    metadata = {
        **source_metadata,
        "detected_at": datetime.now().isoformat(),
        "promoted": False,
    }
    return adhoc_source_object(
        object_name,
        source_type=source_type,
        metadata=metadata,
        columns=columns,
        column_types=column_types,
    )


def promotion_metadata(query_object: QueryObject) -> dict[str, Any]:
    """Return the stable metadata snapshot used when promoting an ad hoc source."""
    source = query_object.sources[0] if query_object.sources else None
    return {
        "name": query_object.name,
        "source_type": source.source_type if source else query_object.source_design,
        "source_metadata": source.metadata if source else {},
        "columns": [
            {
                "name": field.name,
                "data_type": field.data_type,
                "display_name": field.display_name or field.name,
                "role": field.role,
            }
            for field in query_object.fields
        ],
    }


def promote_adhoc_source(
    query_object: QueryObject,
    *,
    status: str = SOURCE_STATUS_REGISTERED,
) -> QueryObject:
    """Mark an ad hoc file object as a registered catalog object."""
    if query_object.kind != OBJECT_KIND_ADHOC_SOURCE:
        raise ValueError("Only ad hoc source objects can be promoted.")

    promoted_at = datetime.now().isoformat()
    query_object.metadata_status = status
    query_object.config["promotion"] = {
        **promotion_metadata(query_object),
        "promoted_at": promoted_at,
    }
    for source in query_object.sources:
        source.status = status
        source.metadata["promoted"] = True
        source.metadata["promoted_at"] = promoted_at
    query_object.updated_at = datetime.now()
    return query_object


def dataframe_from_adhoc_metadata(
    source_type: str,
    metadata: dict[str, Any],
    *,
    columns: list[str] | None = None,
):
    """Load an ad hoc CSV/Excel source into a pandas DataFrame."""
    import pandas as pd

    path = metadata.get("path", "")
    if not path:
        raise ValueError("Ad hoc source is missing a file path.")

    if source_type == "csv":
        df = pd.read_csv(path)
    elif source_type == "excel":
        df = pd.read_excel(path, sheet_name=metadata.get("sheet_name", 0))
    else:
        raise ValueError(f"Unsupported ad hoc source type: {source_type}")

    if columns:
        available = [column for column in columns if column in df.columns]
        if available:
            df = df[available]
    return df


def query_adhoc_object(
    query_object: QueryObject,
    *,
    columns: list[str] | None = None,
    filter_expr: str = "",
    limit: int = 500,
):
    """Load and lightly query a CSV/Excel QueryObject."""
    if query_object.kind != OBJECT_KIND_ADHOC_SOURCE:
        raise ValueError("Only CSV/Excel QueryObjects can be queried this way.")
    source = query_object.sources[0] if query_object.sources else None
    if source is None:
        raise ValueError("File object is missing source metadata.")

    selected_columns = columns or [field.name for field in query_object.fields]
    df = dataframe_from_adhoc_metadata(
        source.source_type,
        source.metadata,
        columns=selected_columns,
    )
    if filter_expr.strip():
        df = df.query(filter_expr.strip(), engine="python")
    if limit > 0:
        df = df.head(limit)
    return df


def _read_csv_sample(path: Path, sample_rows: int) -> tuple[list[str], list[dict[str, Any]]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = []
        for row in reader:
            rows.append(row)
            if len(rows) >= sample_rows:
                break
    return columns, rows


def _read_excel_sample(
    path: Path,
    sample_rows: int,
    sheet_name: str | int | None,
) -> tuple[list[str], list[dict[str, Any]]]:
    import pandas as pd

    df = pd.read_excel(path, sheet_name=sheet_name, nrows=sample_rows)
    columns = [str(column) for column in df.columns]
    rows = df.astype(object).where(pd.notnull(df), "").to_dict(orient="records")
    return columns, rows


def _infer_column_type(values: list[Any]) -> str:
    non_empty = [value for value in values if str(value).strip() != ""]
    if not non_empty:
        return "TEXT"
    if all(_is_integer(value) for value in non_empty):
        return "INTEGER"
    if all(_is_decimal(value) for value in non_empty):
        return "DECIMAL"
    if all(_is_date_like(value) for value in non_empty):
        return "DATE"
    return "TEXT"


def _is_integer(value: Any) -> bool:
    text = str(value).strip()
    try:
        int(text)
        return "." not in text
    except ValueError:
        return False


def _is_decimal(value: Any) -> bool:
    try:
        Decimal(str(value).strip())
        return True
    except (InvalidOperation, ValueError):
        return False


def _is_date_like(value: Any) -> bool:
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            pass
    return False