"""Explicitly allow absent duration-zero metadata; never change cash-value rows.

Usage: venv\\Scripts\\python.exe tools\\rates\\configure_wl_cv_zero_null.py @config.json
Config: {"apply": true, "dsn": "UL_Rates", "output": "..."}
Without apply=true this only validates and reports the current schema.
"""

import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.build_env import guard_data_writable
from suiteview.core.json_store import write_json
from suiteview.ratemanager.whole_life.schema import TABLES
from suiteview.ratemanager.whole_life.service import WholeLifeRepository


def main():
    arg = sys.argv[1]
    config = json.loads(Path(arg[1:]).read_text(encoding="utf-8")) if arg.startswith("@") else json.loads(arg)
    apply = config.get("apply", False)
    if not isinstance(apply, bool):
        raise ValueError("apply must be true or false")
    if apply:
        guard_data_writable("allow absent CVF duration-zero metadata")
    definition = TABLES["WL_RATE_CV"]
    with WholeLifeRepository(config.get("dsn", "UL_Rates")) as repository:
        cursor = repository.connect().cursor()
        try:
            columns = {row.column_name: row for row in cursor.columns(table=definition.name, schema="dbo")}
            if "DURATION_ZERO_VALUE" not in columns:
                raise ValueError("WL_RATE_CV.DURATION_ZERO_VALUE is missing; create the WL tables first.")
            was_nullable = bool(columns["DURATION_ZERO_VALUE"].nullable)
            repository._validate_table(replace(
                definition, columns=tuple(
                    replace(column, nullable=was_nullable)
                    if column.name == "DURATION_ZERO_VALUE" else column
                    for column in definition.columns
                ),
            ))
            changed = apply and not was_nullable
            if changed:
                cursor.execute("SET XACT_ABORT ON")
                cursor.execute(
                    "ALTER TABLE [dbo].[WL_RATE_CV] "
                    "ALTER COLUMN [DURATION_ZERO_VALUE] decimal(7,2) NULL"
                )
                repository._validate_table(definition)
                repository.commit()
            if apply:
                repository._validate_table(definition)
            report = {
                "database": repository.test_connection(), "apply": apply,
                "column": "WL_RATE_CV.DURATION_ZERO_VALUE",
                "was_nullable": was_nullable, "nullable": was_nullable or changed,
                "schema_changed": changed, "data_rows_changed": 0,
            }
        finally:
            repository.rollback()
            cursor.close()
    if config.get("output"):
        write_json(config["output"], report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
