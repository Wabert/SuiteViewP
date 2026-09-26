"""Pre-change backup writing for Rate Manager loads."""

from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from suiteview.core.json_store import write_json
from suiteview.core.profile_paths import profile_path
from suiteview.ratemanager.package import display_value
from suiteview.ratemanager.plan import ExecutionPlan
from suiteview.ratemanager.schema import RateSchema, UL_SCHEMA



def write_backup(
    plan: ExecutionPlan,
    backup_root: str | Path | None = None,
    schema: RateSchema = UL_SCHEMA,
) -> Optional[Path]:
    rows_to_backup = {
        table: rows for table, rows in plan.backup_rows.items() if rows
    }
    if not rows_to_backup:
        return None
    root = (
        Path(backup_root).expanduser()
        if backup_root is not None
        else profile_path('rate_manager_backups')
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_plancode = re.sub(r"[^A-Za-z0-9_.-]+", "_", plan.plancode).strip("._")
    folder = root / f"{timestamp}_{safe_plancode or 'rate_update'}"
    folder.mkdir(parents=True, exist_ok=False)

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "plancode": plan.plancode,
        "purpose": (
            "Pre-commit backup of rows selected for removal or replacement. "
            "This file alone does not prove the database transaction committed."
        ),
        "actions": {name: action.value for name, action in plan.actions.items()},
        "tables": {},
    }
    for table_name, rows in rows_to_backup.items():
        spec = schema.specs[table_name]
        path = folder / f"{table_name}.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(spec.columns)
            writer.writerows(
                [display_value(value) for value in row] for row in rows
            )
        manifest["tables"][table_name] = {
            "rows": len(rows),
            "file": path.name,
        }
    write_json(folder / "manifest.json", manifest, ensure_ascii=True)
    return folder
