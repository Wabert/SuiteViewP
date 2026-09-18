"""Read-only file intake / persisted source / DuckDB verification, without row output."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.audit import file_query_runner, file_source_store
from suiteview.audit.adhoc_source_intake import dataframe_from_adhoc_metadata
from suiteview.audit.file_source_intake import infer_file_source_from_file, validate_member_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source = infer_file_source_from_file(args.path)
    assert source.source_type == "csv", "This check expects a delimited text file."
    assert not validate_member_file(source, args.path)
    with tempfile.TemporaryDirectory(prefix="suiteview_text_verify_") as directory:
        with patch.dict(os.environ, {"SUITEVIEW_FILE_SOURCES_DIR": directory}):
            file_source_store.save_file_source(source)
            loaded = file_source_store.load_file_source_by_id(source.id)
            assert loaded is not None
            assert loaded.parse_spec == source.parse_spec
            preview = dataframe_from_adhoc_metadata(
                loaded.source_type, loaded.member_metadata(loaded.members[0]), nrows=100)
            table = loaded.table_names[0].replace('"', '""')
            result = file_query_runner.run_sql(
                loaded, f'SELECT COUNT(*) AS row_count FROM "{table}"')
            row_count = int(result.dataframe.iloc[0, 0])

    with args.path.open("r", encoding=source.parse_spec["encoding"], newline="") as handle:
        reader = csv.reader(handle, delimiter=source.parse_spec["delimiter"])
        header = next(reader)
        expected_rows = sum(1 for row in reader if row)
    assert header == source.column_names, "Column names changed during intake."
    assert expected_rows == row_count, "Query row count does not match the input file."
    report = {
        "all_ok": True,
        "file_name": args.path.name,
        "size_bytes": args.path.stat().st_size,
        "encoding": source.parse_spec["encoding"],
        "delimiter": source.parse_spec["delimiter"],
        "column_count": len(source.columns),
        "preview_rows": len(preview),
        "query_row_count": row_count,
        "independent_csv_row_count": expected_rows,
        "saved_source_round_trip": True,
        "source_file_modified": False,
    }
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
