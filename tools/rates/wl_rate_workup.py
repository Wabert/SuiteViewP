r"""Preview, analyze or load source-keyed Whole Life rates using Rate Manager.

Usage: venv\Scripts\python.exe tools\rates\wl_rate_workup.py @config.json

Config: {"action": "preview", "kind": "CVF", "paths": ["C:\\...txt"],
         "user_code": "", "dsn": "UL_Rates", "output": "C:\\...report.json"}
For a combined workup, use "files": {"CVF": [...], "IAF": [...],
    "Dividend": [...], "PUI": [...]} instead of "kind"/"paths".
Optional "infer_cvf_negatives": true enables the audited initial-decline
assumption; it is off by default and keeps the first minimum positive.
Actions: preview (default, no database), analyze, load, create.
Load inserts new rows and refuses changed rows unless their table is explicitly
listed in replace_tables. No action deletes rows or recreates existing tables.
Progress goes to stderr and, when output is configured, a sibling .progress.json.
Only a final verified load report or committed receipt establishes success.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.core.json_store import write_json
from suiteview.ratemanager.package import TableData
from suiteview.ratemanager.whole_life.service import (
    WholeLifeRepository, parse_sources, parse_workup,
)


def _progress(report_path, phase, **details):
    status = {
        "time": datetime.now(timezone.utc).isoformat(), "phase": phase, **details,
    }
    if report_path:
        write_json(Path(report_path).with_suffix(".progress.json"), status)
    print(json.dumps(status), file=sys.stderr, flush=True)


def main() -> None:
    arg = sys.argv[1]
    if arg.startswith("@"):
        with Path(arg[1:]).open(encoding="utf-8-sig") as handle:
            config = json.load(handle)
    else:
        config = json.loads(arg)
    progress = partial(_progress, config.get("output"))
    action = config.get("action", "preview")
    if action not in ("preview", "analyze", "load", "create"):
        raise ValueError(f"Unknown action: {action}")
    report = {"action": action}
    dsn = config.get("dsn", "UL_Rates")
    if action == "create":
        with WholeLifeRepository(dsn) as repository:
            report["created"] = repository.create_tables()
    else:
        progress("parsing")
        if "files" in config:
            if "kind" in config or "paths" in config:
                raise ValueError("Use files for a combined workup, or kind/paths, not both.")
            package = parse_workup(
                config["files"], config.get("user_code", ""),
                infer_cvf_negatives=config.get("infer_cvf_negatives", False),
            )
        else:
            package = parse_sources(
                config["kind"], config["paths"], config.get("user_code", ""),
                infer_cvf_negatives=config.get("infer_cvf_negatives", False),
            )
        report.update({
            "sources": package.sources,
            "row_counts": package.row_counts,
            "package_sha256": package.digest,
            "sample": {
                name: TableData(data.spec, data.rows[:3]).to_records()
                for name, data in package.tables.items()
            },
        })
        progress("parsed", row_counts=package.row_counts, inferred_rows=sum(
            source.get("cvf_inference", {}).get("adjusted_rows", 0)
            for source in package.sources
        ))
        if action in ("analyze", "load"):
            with WholeLifeRepository(dsn) as repository:
                progress("analyzing")
                analysis = repository.analyze(package)
                report["analysis"] = analysis.summary_records()
                progress("analyzed", tables=report["analysis"])
                if action == "load":
                    progress("loading")
                    report["load"] = repository.apply(
                        analysis, set(config.get("replace_tables", []))
                    )
                    progress("committed_and_verified", **report["load"])
                    verified = repository.analyze(package)
                    report["verified"] = all(
                        not row.inserted and not row.changed for row in verified.tables
                    )
                    if not report["verified"]:
                        raise RuntimeError("Post-load analysis differs from the source.")
    if config.get("output"):
        write_json(config["output"], report)
    progress("complete", output=config.get("output"))
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
