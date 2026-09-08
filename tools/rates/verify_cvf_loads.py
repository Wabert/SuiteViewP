"""Verify completed CVF imports against independent header counts and live SQL.

Usage: venv\\Scripts\\python.exe tools\\rates\\verify_cvf_loads.py @config.json
Config: reports, header_reports, dsn (optional), output (optional), samples (optional).
This is read-only; full cell equality is established by each verified load.
"""

import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.json_store import write_json
from suiteview.ratemanager.whole_life.service import WholeLifeRepository


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main():
    arg = sys.argv[1]
    config = read_json(arg[1:]) if arg.startswith("@") else json.loads(arg)
    headers = {}
    expected_rows, expected_schedules, expected_nulls = Counter(), Counter(), Counter()
    for filename in config["header_reports"]:
        for source in read_json(filename)["sources"]:
            if source["path"] in headers:
                raise ValueError(f"Repeated source header report: {source['path']}")
            headers[source["path"]] = source
            for variant in source["variants"]:
                key = (variant["user"], variant["class"])
                expected_rows[key] += variant["rate_cells"]
                expected_schedules[key] += variant["records"]
                if variant["zero"] == "absent":
                    expected_nulls[key] += variant["rate_cells"]
    sources, receipts, inferred = {}, [], Counter()
    for filename in config["reports"]:
        report = read_json(filename)
        if report.get("verified") is not True:
            raise ValueError(f"Load is not fully verified: {filename}")
        receipt = read_json(report["load"]["receipt"])
        if (receipt["status"] != "committed and verified"
                or receipt["package_sha256"] != report["package_sha256"]
                or receipt["sources"] != report["sources"]):
            raise ValueError(f"Receipt does not verify the reported source: {filename}")
        receipts.append(report["load"]["receipt"])
        expected_count = 0
        for source in report["sources"]:
            path = source["path"]
            if path in sources:
                raise ValueError(f"Repeated loaded source: {path}")
            sources[path] = source["sha256"]
            expected_count += headers[path]["rate_cells"]
            audit = source["cvf_inference"]
            if audit["adjusted_rows"] != len(audit["adjustments"]):
                raise ValueError(f"Inference count differs from the audit: {path}")
            for row in audit["adjustments"]:
                if not (Decimal(row["printed_rate"]) > 0
                        and Decimal(row["loaded_rate"]) == 0
                        and Decimal(row["header_zero"]) < 0
                        and 0 < row["DURATION"] < row["minimum_duration"]):
                    raise ValueError(f"Invalid early-negative adjustment: {row}")
                inferred[row["USER_CODE"]] += 1
        if report["row_counts"]["WL_RATE_CV"] != expected_count:
            raise ValueError(f"Parsed count differs from source headers: {filename}")
    if sources.keys() != headers.keys():
        raise ValueError("Loaded sources do not cover exactly the selected source headers")
    companies = sorted({key[0] for key in expected_rows})
    with WholeLifeRepository(config.get("dsn", "UL_Rates")) as repository:
        cursor = repository.connect().cursor()
        try:
            cursor.execute(
                "SELECT [USER_CODE], [CLASS], COUNT_BIG(*), "
                "SUM(CASE WHEN [DURATION] = [FIRST_DURATION] THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN [DURATION_ZERO_VALUE] IS NULL THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN [RATE] < 0 OR [DURATION_ZERO_VALUE] < 0 "
                "OR [DURATION] < [FIRST_DURATION] OR [DURATION] > [LAST_DURATION] "
                "OR ([DURATION_ZERO_VALUE] IS NULL AND [DURATION] = 0) THEN 1 ELSE 0 END) "
                "FROM [dbo].[WL_RATE_CV] WHERE [USER_CODE] IN ("
                + ", ".join("?" for _ in companies)
                + ") GROUP BY [USER_CODE], [CLASS] ORDER BY [USER_CODE], [CLASS]",
                companies,
            )
            rows = cursor.fetchall()
            samples = []
            for sample in config.get("samples", []):
                schedule = cursor.execute(
                    "SELECT [DURATION], [RATE], [DURATION_ZERO_VALUE] "
                    "FROM [dbo].[WL_RATE_CV] WHERE [USER_CODE] = ? AND [RATE_KEY] = ? "
                    "AND [ISSUE_AGE] = ? AND [USER_DEFINED] = ? ORDER BY [DURATION]",
                    (sample["company"], sample["key"], sample["age"], sample.get("variant", "")),
                ).fetchall()
                actual_rates = {row[0]: row[1] for row in schedule}
                if (set(actual_rates) != set(range(sample["first"], sample["last"] + 1))
                        or any(actual_rates.get(int(duration)) != Decimal(value)
                               for duration, value in sample["rates"].items())
                        or any((row[2] is None) != sample["zero_is_null"] for row in schedule)):
                    raise ValueError(f"Source sample does not match database: {sample}")
                samples.append({
                    **sample, "verified": True,
                    "actual_rates": {str(duration): str(rate) for duration, rate in actual_rates.items()},
                })
        finally:
            cursor.close()
    actual = {(row[0], row[1]): tuple(row[2:]) for row in rows}
    expected = {
        key: (count, expected_schedules[key], expected_nulls[key], 0)
        for key, count in expected_rows.items()
    }
    if actual != expected:
        raise ValueError(f"Database counts/ranges differ from source headers: {actual!r} != {expected!r}")
    result = {
        "all_ok": True, "database": config.get("dsn", "UL_Rates"),
        "table": "WL_RATE_CV", "total_rates": sum(expected_rows.values()),
        "source_files": sources, "receipts": receipts,
        "inferred_rows_by_company": dict(sorted(inferred.items())),
        "samples": samples,
        "classes": [
            {"company": key[0], "class": key[1], "rates": values[0],
             "schedules": values[1], "absent_zero_metadata": values[2],
             "invalid_rates": values[3]}
            for key, values in sorted(actual.items())
        ],
    }
    if config.get("output"):
        write_json(config["output"], result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
