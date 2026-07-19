"""Saved illustration cases — named input scenarios persisted to disk.

A *case* is the full user input state for an illustration run — everything the
Illustration Inputs tab captures via ``capture_case_inputs()`` (dynamic rows,
grid inputs, run controls, rider decisions, index allocations) — saved under a
user-chosen name so it can be reloaded days later, after the app has closed.
This is the durable sibling of the in-session per-policy state in
``ui/main_window.py`` (which keeps live widgets and is never persisted).

Since schema v2 a case also freezes the policy data it was saved against: the
full ``IllustrationPolicyData`` (``policy_snapshot``) serializes into the file,
so reloading the case later illustrates the policy *as it was when saved* —
no DB2 round trip, no drift from the live policy. v1 files (inputs only)
remain loadable; their ``policy_snapshot`` is ``None`` and the UI must say so.

Storage: one JSON file per case under ``~/.suiteview/illustration_cases/``
(``<slug>.case.json``). There is no separate index — listing scans the folder
and each file self-describes. Writes are atomic (temp file + ``os.replace``)
so a crash can never corrupt a saved case. Loads are LOUD: an unknown schema
version or a corrupt/incomplete file raises — never a silent partial load.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from suiteview import __version__ as _APP_VERSION
from suiteview.illustration.models.policy_data import (
    BenefitInfo,
    CoverageSegment,
    IllustrationPolicyData,
    RiderInfo,
)

# Bump when the payload layout changes, and add an explicit migration in
# _read_case_file for the old number. Loading a file with a version this build
# does not understand raises UnknownCaseVersionError.
#   v1 — inputs-only payload (no frozen policy data).
#   v2 — adds "policy_snapshot": the serialized IllustrationPolicyData the
#        case was saved against (may be null when no policy data was supplied).
CASE_SCHEMA_VERSION = 2
KNOWN_CASE_VERSIONS = (1, 2)
CASE_KIND = "suiteview.illustration.saved_case"
CASE_SUFFIX = ".case.json"


class CaseStoreError(Exception):
    """Base error for saved-case persistence."""


class CaseNotFoundError(CaseStoreError):
    """The named case has no file on disk."""


class CaseExistsError(CaseStoreError):
    """Saving/renaming would overwrite an existing case without permission."""


class CorruptCaseError(CaseStoreError):
    """The case file exists but cannot be read as a complete saved case."""


class UnknownCaseVersionError(CaseStoreError):
    """The case file was written with a schema this build does not know."""


@dataclass(frozen=True)
class SavedCase:
    """One saved case, fully materialized from its file.

    ``policy_snapshot`` is the policy data frozen at save time (schema v2+).
    ``None`` means the case predates snapshots (v1) — the UI must load current
    policy data instead and say so visibly.
    """

    name: str
    policy_number: str
    region: str
    company_code: str
    saved_at: datetime
    app_version: str
    schema_version: int
    inputs: dict
    path: Path = field(compare=False)
    policy_snapshot: Optional[IllustrationPolicyData] = None


def default_cases_dir() -> Path:
    return Path.home() / ".suiteview" / "illustration_cases"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip()).strip("._-")
    if not slug:
        raise CaseStoreError(
            f"Case name {name!r} must contain at least one letter or digit.")
    return slug.lower()


def case_path(name: str, directory: Optional[Path] = None) -> Path:
    """The file a case of this name lives in (whether or not it exists)."""
    directory = Path(directory) if directory else default_cases_dir()
    return directory / f"{_slugify(name)}{CASE_SUFFIX}"


def save_case(
    name: str,
    *,
    policy_number: str,
    region: str,
    company_code: str = "",
    inputs: dict,
    policy_snapshot: Optional[IllustrationPolicyData] = None,
    overwrite: bool = False,
    directory: Optional[Path] = None,
) -> SavedCase:
    """Persist a case atomically. Raises CaseExistsError unless ``overwrite``.

    ``policy_snapshot`` freezes the policy data the case was built against so
    a later load illustrates the policy as it was at save time.
    """
    if not isinstance(inputs, dict):
        raise CaseStoreError(
            f"Case inputs must be a dict, got {type(inputs).__name__}.")
    if not (policy_number or "").strip():
        raise CaseStoreError("A saved case requires a policy number.")
    if policy_snapshot is not None and not isinstance(
            policy_snapshot, IllustrationPolicyData):
        raise CaseStoreError(
            f"policy_snapshot must be IllustrationPolicyData, got "
            f"{type(policy_snapshot).__name__}.")
    path = case_path(name, directory)
    if path.exists() and not overwrite:
        existing = _read_case_file(path)
        raise CaseExistsError(
            f"A saved case named '{existing.name}' already exists.")
    payload = {
        "kind": CASE_KIND,
        "schema_version": CASE_SCHEMA_VERSION,
        "name": str(name).strip(),
        "policy_number": str(policy_number).strip(),
        "region": str(region or "").strip(),
        "company_code": str(company_code or "").strip(),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "app_version": _APP_VERSION,
        "inputs": inputs,
        "policy_snapshot": (
            encode_policy_snapshot(policy_snapshot)
            if policy_snapshot is not None else None),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(path, payload)
    return _case_from_payload(payload, path)


def load_case(name: str, directory: Optional[Path] = None) -> SavedCase:
    path = case_path(name, directory)
    if not path.exists():
        raise CaseNotFoundError(f"No saved case named '{name}' ({path}).")
    return _read_case_file(path)


def list_cases(
    policy_number: Optional[str] = None,
    directory: Optional[Path] = None,
) -> list[SavedCase]:
    """All saved cases, newest first — optionally only one policy's.

    A corrupt or unknown-version file in the folder raises (naming the file)
    rather than being silently skipped.
    """
    folder = Path(directory) if directory else default_cases_dir()
    if not folder.is_dir():
        return []
    cases = [_read_case_file(path) for path in sorted(folder.glob(f"*{CASE_SUFFIX}"))]
    if policy_number is not None:
        wanted = str(policy_number).strip().upper()
        cases = [c for c in cases if c.policy_number.strip().upper() == wanted]
    cases.sort(key=lambda c: c.saved_at, reverse=True)
    return cases


def delete_case(name: str, directory: Optional[Path] = None) -> None:
    path = case_path(name, directory)
    if not path.exists():
        raise CaseNotFoundError(f"No saved case named '{name}' ({path}).")
    path.unlink()


def copy_case(
    source_name: str,
    new_name: str,
    *,
    overwrite: bool = False,
    directory: Optional[Path] = None,
) -> SavedCase:
    """Duplicate a case under a new name with a fresh ``saved_at`` stamp.

    The inputs and any frozen policy snapshot ride through byte-for-byte;
    only the name, saved_at, and app_version are re-stamped (the copy is a
    new file written by this build, now).
    """
    case = load_case(source_name, directory)       # validates loudly
    new_path = case_path(new_name, directory)
    if new_path == case.path:
        raise CaseStoreError(
            "A copy needs a name different from the source case.")
    if new_path.exists() and not overwrite:
        existing = _read_case_file(new_path)
        raise CaseExistsError(
            f"A saved case named '{existing.name}' already exists.")
    payload = json.loads(case.path.read_text(encoding="utf-8"))
    payload["name"] = str(new_name).strip()
    payload["saved_at"] = datetime.now().isoformat(timespec="seconds")
    payload["app_version"] = _APP_VERSION
    _atomic_write_json(new_path, payload)
    return _case_from_payload(payload, new_path)


def rename_case(
    old_name: str,
    new_name: str,
    *,
    overwrite: bool = False,
    directory: Optional[Path] = None,
) -> SavedCase:
    """Rename a case, rewriting its file (atomically) under the new slug.

    The raw payload is preserved byte-for-byte apart from the name — the
    schema version, saved_at stamp, and any frozen policy snapshot ride
    through unchanged.
    """
    case = load_case(old_name, directory)          # validates loudly
    new_path = case_path(new_name, directory)
    if new_path != case.path and new_path.exists() and not overwrite:
        existing = _read_case_file(new_path)
        raise CaseExistsError(
            f"A saved case named '{existing.name}' already exists.")
    payload = json.loads(case.path.read_text(encoding="utf-8"))
    payload["name"] = str(new_name).strip()
    _atomic_write_json(new_path, payload)
    if new_path != case.path:
        case.path.unlink()
    return _case_from_payload(payload, new_path)


# ── internals ────────────────────────────────────────────────────────


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write-temp-then-replace so a crash never leaves a half-written case."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_case_file(path: Path) -> SavedCase:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CaseStoreError(f"Cannot read saved case {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CorruptCaseError(
            f"Saved case {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise CorruptCaseError(f"Saved case {path} is not a JSON object.")
    if data.get("kind") != CASE_KIND:
        raise CorruptCaseError(
            f"Saved case {path} is not a SuiteView illustration case "
            f"(kind={data.get('kind')!r}).")
    version = data.get("schema_version")
    if not isinstance(version, int):
        raise CorruptCaseError(
            f"Saved case {path} has no integer schema_version.")
    if version not in KNOWN_CASE_VERSIONS:
        known = ", ".join(str(v) for v in KNOWN_CASE_VERSIONS)
        raise UnknownCaseVersionError(
            f"Saved case {path} uses schema version {version}; this build "
            f"understands version(s) {known}. It was likely saved by a newer "
            f"SuiteView.")
    return _case_from_payload(data, path)


def _case_from_payload(data: dict, path: Path) -> SavedCase:
    missing = [key for key in ("name", "policy_number", "saved_at", "inputs")
               if not data.get(key)]
    if missing:
        raise CorruptCaseError(
            f"Saved case {path} is missing required field(s): {', '.join(missing)}.")
    inputs = data["inputs"]
    if not isinstance(inputs, dict):
        raise CorruptCaseError(f"Saved case {path} inputs is not an object.")
    try:
        saved_at = datetime.fromisoformat(str(data["saved_at"]))
    except ValueError as exc:
        raise CorruptCaseError(
            f"Saved case {path} has an unreadable saved_at timestamp "
            f"({data['saved_at']!r}).") from exc
    # v1 files carry no snapshot; v2 files carry one (or an explicit null when
    # the case was saved without policy data). A snapshot that cannot decode
    # back into IllustrationPolicyData is corruption — raise, never a silent
    # None.
    snapshot = None
    raw_snapshot = data.get("policy_snapshot")
    if raw_snapshot is not None:
        try:
            snapshot = decode_policy_snapshot(raw_snapshot)
        except Exception as exc:
            raise CorruptCaseError(
                f"Saved case {path} has an unreadable policy snapshot: "
                f"{exc}") from exc
    return SavedCase(
        name=str(data["name"]),
        policy_number=str(data["policy_number"]),
        region=str(data.get("region") or ""),
        company_code=str(data.get("company_code") or ""),
        saved_at=saved_at,
        app_version=str(data.get("app_version") or ""),
        schema_version=int(data["schema_version"]),
        inputs=inputs,
        path=path,
        policy_snapshot=snapshot,
    )


# ── policy snapshot codec ────────────────────────────────────────────
#
# The snapshot must round-trip EXACTLY: dates stay dates, None stays None,
# nested CoverageSegment / BenefitInfo / RiderInfo lists come back as the same
# dataclasses. The codec is explicit about every type it accepts — anything
# else raises rather than silently degrading (a quietly-stringified value
# would poison a later projection).

_SNAPSHOT_TYPES = {
    cls.__name__: cls
    for cls in (IllustrationPolicyData, CoverageSegment, BenefitInfo, RiderInfo)
}


def encode_policy_snapshot(policy: IllustrationPolicyData) -> dict:
    """Serialize an IllustrationPolicyData to a JSON-safe dict."""
    if not isinstance(policy, IllustrationPolicyData):
        raise CaseStoreError(
            f"policy_snapshot must be IllustrationPolicyData, got "
            f"{type(policy).__name__}.")
    return _encode_value(policy)


def decode_policy_snapshot(data: dict) -> IllustrationPolicyData:
    """Rebuild the exact IllustrationPolicyData a snapshot was encoded from."""
    decoded = _decode_value(data)
    if not isinstance(decoded, IllustrationPolicyData):
        raise CaseStoreError(
            "Policy snapshot did not decode to IllustrationPolicyData "
            f"(got {type(decoded).__name__}).")
    return decoded


def _encode_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        # No dataclass field is a datetime today; refuse rather than guess how
        # a future one should round-trip.
        raise CaseStoreError("Policy snapshot cannot serialize datetime values.")
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    if dataclasses.is_dataclass(value) and type(value).__name__ in _SNAPSHOT_TYPES:
        return {
            "__type__": type(value).__name__,
            "fields": {
                f.name: _encode_value(getattr(value, f.name))
                for f in dataclasses.fields(value)
            },
        }
    if isinstance(value, (list, tuple)):
        return [_encode_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _encode_value(item) for key, item in value.items()}
    raise CaseStoreError(
        f"Policy snapshot cannot serialize a {type(value).__name__} value.")


def _decode_value(value):
    if isinstance(value, dict):
        type_name = value.get("__type__")
        if type_name == "date":
            return date.fromisoformat(str(value["value"]))
        if type_name == "decimal":
            return Decimal(str(value["value"]))
        if type_name in _SNAPSHOT_TYPES:
            cls = _SNAPSHOT_TYPES[type_name]
            fields = value.get("fields")
            if not isinstance(fields, dict):
                raise CaseStoreError(
                    f"Snapshot {type_name} entry has no fields object.")
            return cls(**{key: _decode_value(item) for key, item in fields.items()})
        if type_name is not None:
            raise CaseStoreError(
                f"Snapshot contains unknown type marker {type_name!r}.")
        return {key: _decode_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_value(item) for item in value]
    return value
