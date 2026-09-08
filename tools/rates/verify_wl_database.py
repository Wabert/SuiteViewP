r"""Read-only WL schema and typed staging round-trip against live UL_Rates.

No permanent data is changed: three existing rows from each table are staged in
connection-local temporary tables and must compare as entirely unchanged. Empty
tables use one clearly synthetic, temporary schema probe, expected to be new.
"""

from __future__ import annotations

import json
import sys
from collections import OrderedDict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.ratemanager.whole_life.schema import TABLES
from suiteview.ratemanager.whole_life.service import (
    WholeLifeAnalysis, WholeLifePackage, WholeLifeRepository,
)


def main() -> None:
    tables = OrderedDict()
    empty = []
    with WholeLifeRepository() as repository:
        for name, definition in TABLES.items():
            repository._validate_table(definition)
            records = repository.browse(name, {}, 3)
            if records:
                tables[name] = definition.data(records)
            else:
                empty.append(name)
                probe = {}
                for column in definition.columns:
                    kind = column.sql_type
                    if column.nullable:
                        probe[column.name] = None
                    elif kind.startswith("decimal("):
                        probe[column.name] = Decimal("1.25")
                    elif kind in ("smallint", "int"):
                        probe[column.name] = 1
                    elif kind == "date":
                        probe[column.name] = "2000-01-01"
                    elif kind == "float":
                        probe[column.name] = 1.25
                    else:
                        probe[column.name] = "X"
                tables[name] = definition.data([probe])
        package = WholeLifePackage(tables)
        stages = repository._stage(package)
        repository._validate_cvf_ranges(package, stages)
        analysis = WholeLifeAnalysis(
            package, repository._compare(package, stages), package.digest,
            repository.test_connection(),
        )
        all_ok = all(
            not row.changed and row.inserted == (1 if row.table in empty else 0)
            for row in analysis.tables
        )
        report = {
            "all_ok": all_ok, "empty_tables_probed_with_temporary_synthetic_rows": empty,
            "tables": analysis.summary_records(),
        }
        print(json.dumps(report, indent=2))
        if not all_ok:
            raise RuntimeError("WL database staging round-trip did not match.")


if __name__ == "__main__":
    main()
