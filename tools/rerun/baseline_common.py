"""Shared helpers for RERUN/CyberLife baseline evidence tools.

These helpers are intentionally read-only. They support:

* ``baseline_select_policies.py`` selecting varied in-force UL/IUL policies.
* ``baseline_history_compare.py`` replaying recorded monthliversary history.
* ``baseline_workbook.py`` building the saved evidence workbook.

Run scripts from the repository root with
``venv\\Scripts\\python.exe tools\\rerun\\<script>.py ...``.
"""

from __future__ import annotations

import csv
import json
import math
import traceback
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PLANCODE_TABLE = REPO_ROOT / "suiteview" / "illustration" / "plancodes" / "plancode_table.json"
REGION = "CKPR"
SYSTEM_CODE = "I"
EXACT_TOLERANCE = 0.01
ROUNDING_TOLERANCE = 1.00
# RERUN plancode-table entries that are product names, not CyberLife plancodes, and
# the 8-character table row(s) of the same product (the table's former ProductName
# "MLUL"; product names now live in PLAN_DEF.DESCRIPTION).
MLUL_SAME_PRODUCT = {"MLUL": ("1U135F00",), "MLUL502": ("1U135F00",)}


@dataclass(frozen=True)
class RequestedPlancode:
    requested: str
    product_name: str
    cyberlife_plancodes: tuple[str, ...]
    shadow_plancode: str = ""
    resolution_note: str = ""


def parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.startswith("0001") or text.startswith("9999"):
        return None
    return date.fromisoformat(text[:10])


def money(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def classify_diff(diff: float | None) -> str:
    if diff is None:
        return "Not comparable"
    amount = abs(diff)
    if amount <= EXACT_TOLERANCE:
        return "Exact"
    if amount <= ROUNDING_TOLERANCE:
        return "Rounding"
    return "Material"


def traceback_text(limit: int = 8) -> str:
    return "".join(traceback.format_exc(limit=limit))[-4000:]


def read_requested_plancodes(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            code = str(row.get("Plancode", "")).strip().upper()
            if not code:
                continue
            rows.append((code, str(row.get("ProductName", "")).strip()))
    return rows


def plancode_table_rows() -> list[dict[str, Any]]:
    return json.loads(PLANCODE_TABLE.read_text(encoding="utf-8"))["Plancodes"]


def _shadow_plancode(plancode: str) -> str:
    """The legacy CCV plancode (schema PLAN_ATTR SHADOW_LEGACY_PLANCODE, else table fallback)."""
    from suiteview.illustration.models.plancode_config import load_plancode

    return load_plancode(plancode).shadow_plancode


def resolve_requested_plancodes(path: Path) -> list[RequestedPlancode]:
    table_rows = plancode_table_rows()
    by_code = {str(row.get("Plancode", "")).strip().upper(): row for row in table_rows}
    requested_rows = read_requested_plancodes(path)
    resolved: list[RequestedPlancode] = []
    requested_codes = {code for code, _ in requested_rows}
    for code, product in requested_rows:
        row = by_code.get(code)
        shadow = _shadow_plancode(code) if row is not None else ""
        if row is None:
            resolved.append(RequestedPlancode(
                requested=code,
                product_name=product,
                cyberlife_plancodes=(code,),
                shadow_plancode="",
                resolution_note="Not present in plancode_table.json; queried as a CyberLife plancode.",
            ))
            continue
        note = "Direct CyberLife plancode."
        cyberlife = (code,)
        if code in MLUL_SAME_PRODUCT:
            same_product = tuple(c for c in MLUL_SAME_PRODUCT[code] if c not in requested_codes)
            if same_product:
                cyberlife = same_product
                note = (
                    f"{code} is a RERUN plancode-table entry. "
                    f"CyberLife search also includes same-product table row(s): {', '.join(same_product)}."
                )
            else:
                note = (
                    f"{code} is a RERUN plancode-table entry and no separate "
                    "same-product 8-character CyberLife row was found in the table."
                )
        resolved.append(RequestedPlancode(
            requested=code,
            product_name=product,
            cyberlife_plancodes=cyberlife,
            shadow_plancode=shadow,
            resolution_note=note,
        ))
    return resolved


def safe_policy_key(company: str, policy: str) -> str:
    return f"{company.strip()}_{policy.strip()}".replace("/", "_").replace("\\", "_")


def json_dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def json_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def get_git_state() -> dict[str, str]:
    import subprocess

    def run(args: list[str]) -> str:
        try:
            completed = subprocess.run(
                args,
                cwd=REPO_ROOT,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            return f"unavailable: {exc}"
        text = (completed.stdout or completed.stderr or "").strip()
        return text[:4000]

    head = run(["git", "--no-pager", "rev-parse", "HEAD"])
    status = run(["git", "--no-pager", "status", "--short"])
    return {
        "head": head,
        "working_tree": "uncommitted working tree" if status else "clean working tree",
        "status_short": status,
    }


ENGINE_STATE_FILES = (
    "suiteview/illustration/core/calc_engine.py",
    "suiteview/illustration/core/rate_loader.py",
    "suiteview/illustration/core/ul_rates.py",
    "suiteview/illustration/core/declared_rates.py",
    "suiteview/illustration/core/interest_calc.py",
    "suiteview/illustration/core/monthly_deduction.py",
    "suiteview/illustration/core/premium_allowance.py",
    "suiteview/illustration/core/withdrawal_handler.py",
    "suiteview/illustration/core/loan_handler.py",
    "suiteview/illustration/core/shadow_calc.py",
    "suiteview/illustration/core/value_rollback.py",
    "suiteview/illustration/plancodes/plancode_table.json",
    "suiteview/polview/models/schema_rates.py",
    "tools/rerun/baseline_history_compare.py",
)


def code_fingerprint() -> dict[str, Any]:
    """Identify the exact code state a baseline ran on (HEAD + uncommitted working tree).

    ``tracked_diff_sha256`` hashes ``git diff HEAD`` (tracked changes);
    ``untracked_sha256`` hashes the paths and contents of untracked files under
    ``suiteview/`` and ``tools/rerun/``; ``files`` gives SHA-256 of the engine and
    rate-loader files the replay depends on. A clean HEAD checkout reproduces the
    run only when both diff hashes are empty.
    """
    import hashlib
    import subprocess

    def git(args: list[str]) -> bytes:
        try:
            return subprocess.run(["git", "--no-pager", *args], cwd=REPO_ROOT, check=False,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
        except OSError:
            return b""

    head = git(["rev-parse", "HEAD"]).decode("utf-8", "replace").strip()
    status = git(["status", "--short"]).decode("utf-8", "replace").splitlines()
    tracked = git(["diff", "HEAD", "--binary"])
    untracked_paths = sorted(
        line[3:].strip() for line in status
        if line.startswith("??") and (line[3:].startswith("suiteview/") or line[3:].startswith("tools/rerun/"))
    )
    untracked_hash = hashlib.sha256()
    for rel in untracked_paths:
        path = REPO_ROOT / rel
        if path.is_file():
            untracked_hash.update(rel.encode("utf-8"))
            untracked_hash.update(path.read_bytes())
    files = {}
    for rel in ENGINE_STATE_FILES:
        path = REPO_ROOT / rel
        files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else "missing"
    return {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "head": head,
        "modified_tracked_files": sum(1 for line in status if not line.startswith("??")),
        "untracked_entries": sum(1 for line in status if line.startswith("??")),
        "tracked_diff_sha256": hashlib.sha256(tracked).hexdigest()[:16] if tracked else "",
        "untracked_sha256": untracked_hash.hexdigest()[:16] if untracked_paths else "",
        "untracked_suiteview_tools_rerun": untracked_paths,
        "files": files,
    }


RATES_REPO = Path(r"C:\Users\ab7y02\Dev\Cyberlife_Rates\Rates_Database")


def rate_state_note(rates_repo: Path = RATES_REPO) -> dict[str, Any]:
    """Describe the UL_Rates loader state from the rates repository's run log (read-only).

    Records whether the loader's ``LOAD.lock`` is present, the newest bulk-load run
    report and the last-modified time of the loader progress log. This is a file
    based marker; UL_Rates itself is only read by the engine.
    """
    bulk = rates_repo / "results" / "bulk"
    runs = sorted((p for p in (bulk / "runs").glob("*") if p.is_dir()), key=lambda p: p.name) if (bulk / "runs").exists() else []
    progress = rates_repo / "review" / "bulk-loader-progress.md"
    return {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "load_lock_present": (bulk / "LOAD.lock").exists(),
        "latest_run_report": str(runs[-1] / "report.json") if runs else "",
        "latest_run_mtime": datetime.fromtimestamp(runs[-1].stat().st_mtime).isoformat(timespec="seconds") if runs else "",
        "progress_log_mtime": (
            datetime.fromtimestamp(progress.stat().st_mtime).isoformat(timespec="seconds") if progress.exists() else ""
        ),
    }
