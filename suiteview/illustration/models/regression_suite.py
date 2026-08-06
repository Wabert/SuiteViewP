"""Portable illustration regression-suite packages.

A ``.svreg`` file is a ZIP containing frozen schema-v2 saved cases and up to
two complete baseline revisions: the active revision and one rollback copy.
Every member is checksummed and suite replacement is atomic.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Optional

from suiteview import __version__ as APP_VERSION
from suiteview.illustration.core.summary_results import (
    ALL_COLUMNS,
    SUMMARY_SCHEMA_VERSION,
)
from suiteview.illustration.models.case_store import (
    SavedCase,
    decode_saved_case,
    encode_saved_case,
)

SUITE_KIND = "suiteview.illustration.regression_suite"
RESULT_KIND = "suiteview.illustration.regression_result"
SUITE_SCHEMA_VERSION = 1
SUITE_SUFFIX = ".svreg"
RESULT_SUFFIX = ".svreg-result"
BASES = ("current", "guaranteed")


class RegressionSuiteError(Exception):
    """A regression suite is invalid or cannot be persisted."""


@dataclass
class SuiteCase:
    case_id: str
    case: SavedCase


@dataclass
class BaselineRevision:
    revision: int
    approved_at: str
    app_version: str
    provenance: dict = field(default_factory=dict)
    rows: dict = field(default_factory=dict)


@dataclass
class RegressionSuite:
    suite_id: str
    name: str
    created_at: str
    updated_at: str
    cases: list[SuiteCase]
    active: Optional[BaselineRevision] = None
    previous: Optional[BaselineRevision] = None
    path: Optional[Path] = field(default=None, compare=False)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create_suite(name: str, cases: list[SavedCase]) -> RegressionSuite:
    cleaned = str(name or "").strip()
    if not cleaned:
        raise RegressionSuiteError("A regression suite requires a name.")
    if not cases:
        raise RegressionSuiteError("A regression suite requires at least one case.")
    entries = []
    for case in cases:
        if case.schema_version != 2 or case.policy_snapshot is None:
            raise RegressionSuiteError(
                f"Case '{case.name}' has no frozen schema-v2 policy snapshot.")
        entries.append(SuiteCase(uuid.uuid4().hex, case))
    stamp = _now()
    return RegressionSuite(
        suite_id=str(uuid.uuid4()), name=cleaned, created_at=stamp,
        updated_at=stamp, cases=entries)


def _json_bytes(value) -> bytes:
    try:
        text = json.dumps(
            value, ensure_ascii=True, allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise RegressionSuiteError(f"Suite contains non-JSON data: {exc}") from exc
    return text.encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_member_name(name: str) -> None:
    path = PurePosixPath(name)
    if not name or "\\" in name or path.is_absolute() or ".." in path.parts:
        raise RegressionSuiteError(f"Unsafe suite member path: {name!r}.")


def _validate_rows(rows: list, label: str) -> None:
    if not isinstance(rows, list):
        raise RegressionSuiteError(f"{label} baseline is not a row list.")
    seen = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or tuple(row.keys()) != ALL_COLUMNS:
            raise RegressionSuiteError(
                f"{label} row {index} does not match Summary schema "
                f"version {SUMMARY_SCHEMA_VERSION}.")
        key = (row["Date"], row["Year"], row["Month"])
        if key in seen:
            raise RegressionSuiteError(f"{label} contains duplicate row {key}.")
        seen.add(key)
        _json_bytes(row)


def _revision_members(slot: str, revision: Optional[BaselineRevision]) -> tuple[dict, dict]:
    if revision is None:
        return {}, {}
    members = {}
    case_ids = []
    for case_id, bases in revision.rows.items():
        if not isinstance(bases, dict) or set(bases) != set(BASES):
            raise RegressionSuiteError(
                f"Baseline revision {revision.revision} case {case_id} must "
                "contain current and guaranteed rows.")
        case_ids.append(case_id)
        for basis in BASES:
            rows = bases[basis]
            _validate_rows(rows, f"{slot}/{case_id}/{basis}")
            member = f"baselines/{slot}/{case_id}/{basis}.json"
            members[member] = _json_bytes(rows)
    metadata = {
        "revision": revision.revision,
        "approved_at": revision.approved_at,
        "app_version": revision.app_version,
        "provenance": revision.provenance,
        "case_ids": sorted(case_ids),
    }
    return members, metadata


def _build_members(suite: RegressionSuite) -> dict[str, bytes]:
    members: dict[str, bytes] = {}
    case_meta = []
    valid_case_ids = set()
    for entry in suite.cases:
        if entry.case_id in valid_case_ids:
            raise RegressionSuiteError(f"Duplicate suite case id {entry.case_id}.")
        valid_case_ids.add(entry.case_id)
        if entry.case.schema_version != 2 or entry.case.policy_snapshot is None:
            raise RegressionSuiteError(
                f"Case '{entry.case.name}' has no frozen schema-v2 snapshot.")
        member = f"cases/{entry.case_id}.case.json"
        members[member] = _json_bytes(encode_saved_case(entry.case))
        case_meta.append({
            "case_id": entry.case_id,
            "member": member,
            "name": entry.case.name,
            "policy_number": entry.case.policy_number,
        })

    active_members, active_meta = _revision_members("current", suite.active)
    previous_members, previous_meta = _revision_members("previous", suite.previous)
    members.update(active_members)
    members.update(previous_members)
    baseline_ids = set()
    if suite.active:
        baseline_ids.update(suite.active.rows)
    if suite.previous:
        baseline_ids.update(suite.previous.rows)
    unknown = baseline_ids - valid_case_ids
    if unknown:
        raise RegressionSuiteError(
            f"Baseline contains unknown case id(s): {', '.join(sorted(unknown))}.")

    manifest = {
        "kind": SUITE_KIND,
        "schema_version": SUITE_SCHEMA_VERSION,
        "suite_id": suite.suite_id,
        "name": suite.name,
        "created_at": suite.created_at,
        "updated_at": suite.updated_at,
        "app_version": APP_VERSION,
        "summary_schema_version": SUMMARY_SCHEMA_VERSION,
        "summary_columns": list(ALL_COLUMNS),
        "cases": case_meta,
        "active_baseline": active_meta or None,
        "previous_baseline": previous_meta or None,
        "checksums": {name: _digest(data) for name, data in sorted(members.items())},
    }
    members["manifest.json"] = _json_bytes(manifest)
    return members


def save_suite(suite: RegressionSuite, path: Path | str | None = None) -> RegressionSuite:
    target = Path(path or suite.path or "")
    if not str(target):
        raise RegressionSuiteError("No regression suite path was supplied.")
    if target.suffix.lower() != SUITE_SUFFIX:
        target = target.with_suffix(SUITE_SUFFIX)
    target.parent.mkdir(parents=True, exist_ok=True)
    members = _build_members(suite)
    temporary = target.with_name(target.name + ".tmp")
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for name, data in sorted(members.items()):
                archive.writestr(name, data)
        os.replace(temporary, target)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        finally:
            raise
    suite.path = target
    return suite


def _read_json(archive: zipfile.ZipFile, name: str):
    try:
        return json.loads(archive.read(name).decode("utf-8"), object_pairs_hook=dict)
    except KeyError as exc:
        raise RegressionSuiteError(f"Suite is missing {name}.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegressionSuiteError(f"Suite member {name} is not valid JSON: {exc}") from exc


def _load_revision(archive, slot: str, metadata: Optional[dict]) -> Optional[BaselineRevision]:
    if metadata is None:
        return None
    required = ("revision", "approved_at", "app_version", "case_ids")
    if not isinstance(metadata, dict) or any(key not in metadata for key in required):
        raise RegressionSuiteError(f"Suite {slot} baseline metadata is incomplete.")
    rows = {}
    for case_id in metadata["case_ids"]:
        bases = {}
        for basis in BASES:
            member = f"baselines/{slot}/{case_id}/{basis}.json"
            bases[basis] = _read_json(archive, member)
            _validate_rows(bases[basis], f"{slot}/{case_id}/{basis}")
        rows[str(case_id)] = bases
    return BaselineRevision(
        revision=int(metadata["revision"]),
        approved_at=str(metadata["approved_at"]),
        app_version=str(metadata["app_version"]),
        provenance=dict(metadata.get("provenance") or {}),
        rows=rows,
    )


def load_suite(path: Path | str) -> RegressionSuite:
    source = Path(path)
    try:
        with zipfile.ZipFile(source, "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise RegressionSuiteError("Suite contains duplicate member names.")
            for name in names:
                _validate_member_name(name)
            manifest = _read_json(archive, "manifest.json")
            if manifest.get("kind") != SUITE_KIND:
                raise RegressionSuiteError("File is not a SuiteView regression suite.")
            if manifest.get("schema_version") != SUITE_SCHEMA_VERSION:
                raise RegressionSuiteError(
                    f"Unsupported regression suite schema "
                    f"{manifest.get('schema_version')!r}.")
            if manifest.get("summary_schema_version") != SUMMARY_SCHEMA_VERSION:
                raise RegressionSuiteError("Suite uses an unsupported Summary schema.")
            if tuple(manifest.get("summary_columns") or ()) != ALL_COLUMNS:
                raise RegressionSuiteError("Suite Summary columns do not match this build.")

            checksums = manifest.get("checksums")
            if not isinstance(checksums, dict):
                raise RegressionSuiteError("Suite has no checksum table.")
            expected_names = {"manifest.json", *checksums.keys()}
            if set(names) != expected_names:
                raise RegressionSuiteError("Suite members do not match its manifest.")
            for name, expected in checksums.items():
                actual = _digest(archive.read(name))
                if actual != expected:
                    raise RegressionSuiteError(f"Checksum mismatch for {name}.")

            entries = []
            case_ids = set()
            for metadata in manifest.get("cases") or []:
                case_id = str(metadata.get("case_id") or "")
                member = str(metadata.get("member") or "")
                if not case_id or case_id in case_ids:
                    raise RegressionSuiteError("Suite contains duplicate or empty case ids.")
                case_ids.add(case_id)
                case = decode_saved_case(_read_json(archive, member), Path(member))
                if case.schema_version != 2 or case.policy_snapshot is None:
                    raise RegressionSuiteError(
                        f"Case '{case.name}' has no frozen schema-v2 snapshot.")
                entries.append(SuiteCase(case_id, case))

            active = _load_revision(archive, "current", manifest.get("active_baseline"))
            previous = _load_revision(archive, "previous", manifest.get("previous_baseline"))
    except (OSError, zipfile.BadZipFile) as exc:
        raise RegressionSuiteError(f"Cannot read regression suite {source}: {exc}") from exc

    suite = RegressionSuite(
        suite_id=str(manifest.get("suite_id") or ""),
        name=str(manifest.get("name") or ""),
        created_at=str(manifest.get("created_at") or ""),
        updated_at=str(manifest.get("updated_at") or ""),
        cases=entries,
        active=active,
        previous=previous,
        path=source,
    )
    known = {entry.case_id for entry in entries}
    for revision in (active, previous):
        if revision and not set(revision.rows).issubset(known):
            raise RegressionSuiteError("Baseline refers to a case not in the suite.")
    return suite


def update_baseline(
    suite: RegressionSuite,
    actual_rows: dict,
    case_ids: Optional[list[str]] = None,
    *,
    provenance: Optional[dict] = None,
) -> RegressionSuite:
    """Promote selected successful actual rows and retain one prior revision."""
    selected = list(case_ids or actual_rows.keys())
    known = {entry.case_id for entry in suite.cases}
    if not selected:
        raise RegressionSuiteError("No cases were selected for baseline update.")
    unknown = set(selected) - known
    if unknown:
        raise RegressionSuiteError(
            f"Unknown case id(s): {', '.join(sorted(unknown))}.")
    for case_id in selected:
        bases = actual_rows.get(case_id)
        if not isinstance(bases, dict) or set(bases) != set(BASES):
            raise RegressionSuiteError(
                f"Case {case_id} has no complete current/guaranteed candidate.")
        for basis in BASES:
            _validate_rows(bases[basis], f"candidate/{case_id}/{basis}")

    candidate = copy.deepcopy(suite)
    prior_rows = copy.deepcopy(candidate.active.rows) if candidate.active else {}
    for case_id in selected:
        prior_rows[case_id] = copy.deepcopy(actual_rows[case_id])
    revision = (candidate.active.revision + 1) if candidate.active else 1
    candidate.previous = copy.deepcopy(candidate.active)
    candidate.active = BaselineRevision(
        revision=revision,
        approved_at=_now(),
        app_version=APP_VERSION,
        provenance=copy.deepcopy(provenance or {}),
        rows=prior_rows,
    )
    candidate.updated_at = _now()
    return save_suite(candidate, suite.path)


def undo_baseline_update(suite: RegressionSuite) -> RegressionSuite:
    """Swap the active and single previous baseline revisions atomically."""
    if suite.previous is None:
        raise RegressionSuiteError("This suite has no previous baseline revision.")
    candidate = copy.deepcopy(suite)
    candidate.active, candidate.previous = candidate.previous, candidate.active
    candidate.updated_at = _now()
    return save_suite(candidate, suite.path)


def save_run_result(
    suite: RegressionSuite,
    run,
    path: Path | str,
) -> Path:
    """Write a completed run and its diffs as an immutable audit package."""
    target = Path(path)
    if not str(target).lower().endswith(RESULT_SUFFIX):
        target = Path(str(target) + RESULT_SUFFIX)
    members = {}
    case_metadata = []
    for result in run.cases:
        actual_members = {}
        for basis_name, basis_result in (
            ("current", result.current),
            ("guaranteed", result.guaranteed),
        ):
            member = f"actual/{result.case_id}/{basis_name}.json"
            members[member] = _json_bytes(basis_result.rows)
            actual_members[basis_name] = member
        case_metadata.append({
            "case_id": result.case_id,
            "name": result.name,
            "policy_number": result.policy_number,
            "current_status": result.current.status,
            "guaranteed_status": result.guaranteed.status,
            "current_error": result.current.error,
            "guaranteed_error": result.guaranteed.error,
            "actual": actual_members,
        })
    diffs = [
        {
            "case_id": diff.case_id,
            "case_name": diff.case_name,
            "basis": diff.basis,
            "date": diff.date,
            "year": diff.year,
            "month": diff.month,
            "field": diff.field,
            "expected": diff.expected,
            "actual": diff.actual,
            "delta": diff.delta,
            "tolerance": diff.tolerance,
            "kind": diff.kind,
        }
        for diff in run.diffs
    ]
    members["differences.json"] = _json_bytes(diffs)
    manifest = {
        "kind": RESULT_KIND,
        "schema_version": SUITE_SCHEMA_VERSION,
        "suite_id": suite.suite_id,
        "suite_name": suite.name,
        "baseline_revision": run.baseline_revision,
        "baseline_approved_at": run.baseline_approved_at,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "app_version": run.app_version,
        "cancelled": run.cancelled,
        "provenance": run.provenance,
        "summary_schema_version": SUMMARY_SCHEMA_VERSION,
        "summary_columns": list(ALL_COLUMNS),
        "cases": case_metadata,
        "differences_member": "differences.json",
        "checksums": {name: _digest(data) for name, data in sorted(members.items())},
    }
    members["manifest.json"] = _json_bytes(manifest)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for name, data in sorted(members.items()):
                archive.writestr(name, data)
        os.replace(temporary, target)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        finally:
            raise
    return target
