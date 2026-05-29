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

_EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xls"}
_TEXT_SUFFIXES = {".csv", ".txt", ".dat", ".psv", ".tsv"}
_SUPPORTED_SUFFIXES = _TEXT_SUFFIXES | _EXCEL_SUFFIXES


def delimited_text_spec(
    *,
    delimiter: str = ",",
    has_header: bool = True,
    column_names: list[str] | None = None,
    encoding: str = "utf-8-sig",
    skip_rows: int = 0,
) -> dict[str, Any]:
    """Build metadata for a delimited text source."""
    return {
        "format": "delimited",
        "delimiter": delimiter,
        "has_header": has_header,
        "column_names": column_names or [],
        "encoding": encoding,
        "skip_rows": skip_rows,
    }


def fixed_width_spec(
    columns: list[dict[str, Any]],
    *,
    encoding: str = "utf-8-sig",
    skip_rows: int = 0,
) -> dict[str, Any]:
    """Build metadata for a fixed-width text source."""
    return {
        "format": "fixed_width",
        "columns": columns,
        "encoding": encoding,
        "skip_rows": skip_rows,
    }


def query_object_from_file(
    path: str | Path,
    *,
    name: str | None = None,
    sample_rows: int = 100,
    sheet_name: str | int | None = 0,
    format_spec: dict[str, Any] | None = None,
) -> QueryObject:
    """Infer a temporary QueryObject from a loose file source."""
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix not in _SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(_SUPPORTED_SUFFIXES))
        raise ValueError(f"Unsupported ad hoc source type: {suffix}. Supported: {supported}")

    if suffix in _EXCEL_SUFFIXES:
        columns, rows = _read_excel_sample(file_path, sample_rows, sheet_name)
        source_type = "excel"
        source_metadata = {
            "path": str(file_path),
            "sheet_name": sheet_name,
            "sample_rows": len(rows),
        }
    else:
        resolved_spec = _resolve_text_format_spec(file_path, format_spec)
        columns, rows = _read_text_sample(file_path, sample_rows, resolved_spec)
        source_type = "fixed_width" if resolved_spec.get("format") == "fixed_width" else "csv"
        source_metadata = {
            "path": str(file_path),
            "sample_rows": len(rows),
            **resolved_spec,
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


def replace_adhoc_source_path(
    query_object: QueryObject,
    path: str | Path,
    *,
    sample_rows: int = 25,
) -> QueryObject:
    """Swap the backing file path without changing parser settings or columns."""
    if query_object.kind != OBJECT_KIND_ADHOC_SOURCE:
        raise ValueError("Only file source QueryObjects can change source files.")
    source = query_object.sources[0] if query_object.sources else None
    if source is None:
        raise ValueError("File object is missing source metadata.")

    new_metadata = dict(source.metadata)
    new_metadata["path"] = str(Path(path))
    if (
        source.source_type == "csv"
        and new_metadata.get("format") == "delimited"
        and not bool(new_metadata.get("has_header", True))
        and not new_metadata.get("column_names")
    ):
        new_metadata["column_names"] = [field.name for field in query_object.fields]

    sample = _dataframe_from_source_metadata(source.source_type, new_metadata, nrows=sample_rows)
    missing = [field.name for field in query_object.fields if field.name not in sample.columns]
    if missing:
        missing_text = ", ".join(missing[:10])
        if len(missing) > 10:
            missing_text += ", ..."
        raise ValueError(
            "The new file does not match this QueryObject's saved columns. "
            f"Missing: {missing_text}"
        )

    source.metadata = new_metadata
    query_object.config["source_metadata"] = new_metadata
    query_object.updated_at = datetime.now()
    return query_object


def dataframe_from_adhoc_metadata(
    source_type: str,
    metadata: dict[str, Any],
    *,
    columns: list[str] | None = None,
):
    """Load an ad hoc file source into a pandas DataFrame."""
    df = _dataframe_from_source_metadata(source_type, metadata)

    if columns:
        available = [column for column in columns if column in df.columns]
        if available:
            df = df[available]
    return df


def _dataframe_from_source_metadata(
    source_type: str,
    metadata: dict[str, Any],
    *,
    nrows: int | None = None,
):
    import pandas as pd

    path = metadata.get("path", "")
    if not path:
        raise ValueError("Ad hoc source is missing a file path.")

    if source_type == "csv":
        return _read_delimited_dataframe(path, metadata, nrows=nrows)
    if source_type == "excel":
        return pd.read_excel(path, sheet_name=metadata.get("sheet_name", 0), nrows=nrows)
    if source_type == "fixed_width":
        return _read_fixed_width_dataframe(path, metadata, nrows=nrows)
    raise ValueError(f"Unsupported ad hoc source type: {source_type}")


def query_adhoc_object(
    query_object: QueryObject,
    *,
    columns: list[str] | None = None,
    filter_expr: str = "",
    limit: int = 500,
):
    """Load and lightly query a file-backed QueryObject."""
    if query_object.kind != OBJECT_KIND_ADHOC_SOURCE:
        raise ValueError("Only file source QueryObjects can be queried this way.")
    source = query_object.sources[0] if query_object.sources else None
    if source is None:
        raise ValueError("File object is missing source metadata.")

    selected_columns = columns or [field.name for field in query_object.fields]
    df = dataframe_from_adhoc_metadata(
        source.source_type,
        source.metadata,
        columns=None if filter_expr.strip() else selected_columns,
    )
    if filter_expr.strip():
        df = df.query(filter_expr.strip(), engine="python")
        available = [column for column in selected_columns if column in df.columns]
        if available:
            df = df[available]
    if limit > 0:
        df = df.head(limit)
    return df


def _read_text_sample(
    path: Path,
    sample_rows: int,
    format_spec: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    if format_spec.get("format") == "fixed_width":
        df = _read_fixed_width_dataframe(path, format_spec, nrows=sample_rows)
    else:
        df = _read_delimited_dataframe(path, format_spec, nrows=sample_rows)
    columns = [str(column) for column in df.columns]
    rows = df.astype(object).where(df.notnull(), "").to_dict(orient="records")
    return columns, rows


def _resolve_text_format_spec(path: Path, format_spec: dict[str, Any] | None) -> dict[str, Any]:
    if format_spec:
        resolved = dict(format_spec)
        if resolved.get("format") == "fixed_width":
            _validate_fixed_width_columns(resolved.get("columns", []))
        return resolved
    if path.suffix.lower() == ".csv":
        return delimited_text_spec(delimiter=",")
    delimiter = _sniff_delimiter(path)
    return delimited_text_spec(delimiter=delimiter)


def _sniff_delimiter(path: Path) -> str:
    try:
        sample = path.read_text(encoding="utf-8-sig", errors="replace")[:8192]
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", "\t", "|", ";", "~"])
        return dialect.delimiter
    except Exception:
        return ","


def _read_delimited_dataframe(
    path: str | Path,
    metadata: dict[str, Any],
    *,
    nrows: int | None = None,
):
    import pandas as pd

    delimiter = metadata.get("delimiter", ",")
    has_header = bool(metadata.get("has_header", True))
    encoding = metadata.get("encoding", "utf-8-sig")
    skip_rows = int(metadata.get("skip_rows", 0) or 0)
    df = pd.read_csv(
        path,
        sep=delimiter,
        header=0 if has_header else None,
        encoding=encoding,
        skiprows=skip_rows,
        nrows=nrows,
    )
    column_names = _normalized_column_names(metadata.get("column_names", []))
    if column_names:
        if len(column_names) != len(df.columns):
            raise ValueError(
                f"Column name count ({len(column_names)}) does not match file column count ({len(df.columns)})."
            )
        df.columns = column_names
    elif not has_header:
        df.columns = [str(column) for column in df.columns]
    return df


def _normalized_column_names(column_names: list[Any]) -> list[str]:
    names = [str(name).strip() for name in column_names if str(name).strip()]
    if len(names) != len(set(name.lower() for name in names)):
        raise ValueError("Column names must be unique.")
    return names


def _read_fixed_width_dataframe(
    path: str | Path,
    metadata: dict[str, Any],
    *,
    nrows: int | None = None,
):
    import pandas as pd

    columns = _validate_fixed_width_columns(metadata.get("columns", []))
    names = [str(column["name"]) for column in columns]
    colspecs = [
        (int(column["start"]) - 1, int(column["start"]) - 1 + int(column["width"]))
        for column in columns
    ]
    df = pd.read_fwf(
        path,
        colspecs=colspecs,
        names=names,
        header=None,
        encoding=metadata.get("encoding", "utf-8-sig"),
        skiprows=int(metadata.get("skip_rows", 0) or 0),
        nrows=nrows,
    )
    return df


def _validate_fixed_width_columns(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not columns:
        raise ValueError("Fixed-width text sources require at least one column specification.")
    for column in columns:
        name = str(column.get("name", "")).strip()
        start = int(column.get("start", 0) or 0)
        width = int(column.get("width", 0) or 0)
        if not name or start < 1 or width < 1:
            raise ValueError("Fixed-width columns must include name, 1-based start, and positive width.")
        column["name"] = name
        column["start"] = start
        column["width"] = width
    return columns


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