"""Readable, portable illustration case bundles (``.cases.json``).

A *bundle* is a plain, pretty-printed JSON file holding one or more saved
illustration cases — the transparent, human-readable alternative to the opaque
``.svreg`` regression-suite ZIP. Every export uses the SAME shape: an envelope
object with a ``cases`` array. A single-case export is simply a bundle of one,
so import never has to branch on single vs. many.

Each case entry is exactly the schema-v2 ``encode_saved_case`` payload (the
illustration inputs plus the frozen ``policy_snapshot`` — policy record + the
illustrated interest rates used at save time). The large static product
rate-file data (COIs, expense-per-unit, surrender charges) is never part of a
case, so it never travels in a bundle; it is reloaded from the rate tables at
run time.

Reads are LOUD but granular: a malformed envelope raises, while a file whose
envelope is sound but whose individual cases are a mix of valid and invalid is
reported as both (``cases`` for the good ones, ``errors`` for the bad ones) so
the UI can let the user import the valid subset, refuse the whole file, or
accept it anyway. Writes are atomic (temp file + ``os.replace``).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from suiteview import __version__ as _APP_VERSION
from suiteview.illustration.models.case_store import (
    CaseStoreError,
    SavedCase,
    decode_saved_case,
    encode_saved_case,
)

BUNDLE_KIND = "suiteview.illustration.case_bundle"
BUNDLE_SCHEMA_VERSION = 1
KNOWN_BUNDLE_VERSIONS = (1,)
BUNDLE_SUFFIX = ".cases.json"


class CaseBundleError(Exception):
    """The bundle envelope is malformed or cannot be persisted."""


@dataclass
class BundleReadResult:
    """The outcome of reading a bundle file.

    ``cases`` are the cases that decoded cleanly, in file order. ``errors`` is
    one ``(index, message)`` per case entry that could not decode — the index
    is the position in the file's ``cases`` array so the UI can name it. A file
    with no ``errors`` imported perfectly; a file with some of each is the
    mixed case the caller must resolve.
    """

    name: str
    cases: list[SavedCase]
    errors: list[tuple[int, str]] = field(default_factory=list)
    app_version: str = ""
    exported_at: str = ""
    source: Optional[Path] = None

    @property
    def total(self) -> int:
        return len(self.cases) + len(self.errors)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


def default_bundle_name(cases: list[SavedCase]) -> str:
    """A sensible pre-fill name for an export of these cases."""
    if len(cases) == 1:
        return cases[0].name
    return f"{len(cases)} cases"


def encode_bundle(cases: list[SavedCase], *, name: str = "") -> dict:
    """Return the JSON-safe envelope for these saved cases."""
    if not cases:
        raise CaseBundleError("A case bundle needs at least one case.")
    encoded = []
    for case in cases:
        if not isinstance(case, SavedCase):
            raise CaseBundleError(
                f"A bundle case must be a SavedCase, got {type(case).__name__}.")
        try:
            encoded.append(encode_saved_case(case))
        except CaseStoreError as exc:
            raise CaseBundleError(
                f"Cannot encode case '{case.name}': {exc}") from exc
    return {
        "kind": BUNDLE_KIND,
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "name": str(name or "").strip(),
        "app_version": _APP_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "cases": encoded,
    }


def write_bundle(
    path: Path | str,
    cases: list[SavedCase],
    *,
    name: str = "",
) -> Path:
    """Write these cases as a pretty-printed ``.cases.json`` bundle, atomically."""
    target = Path(path)
    if not target.name.lower().endswith(BUNDLE_SUFFIX):
        # Replace a bare .json (from a save dialog) or add the suffix outright,
        # so every export lands as a self-describing .cases.json.
        stem = target.name[:-5] if target.name.lower().endswith(".json") else target.name
        target = target.with_name(stem + BUNDLE_SUFFIX)
    payload = encode_bundle(cases, name=name)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return target


def read_bundle(path: Path | str) -> BundleReadResult:
    """Read a bundle file. Raises on a malformed envelope; collects per-case
    decode failures into the result rather than aborting the whole file."""
    source = Path(path)
    try:
        raw = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise CaseBundleError(f"Cannot read bundle {source}: {exc}") from exc
    return decode_bundle(raw, source)


def decode_bundle(raw: str, source: Optional[Path] = None) -> BundleReadResult:
    """Validate a bundle's envelope and materialize its cases (granular)."""
    where = source if source is not None else Path("<bundle>")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CaseBundleError(f"Bundle {where} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise CaseBundleError(f"Bundle {where} is not a JSON object.")
    if data.get("kind") != BUNDLE_KIND:
        raise CaseBundleError(
            f"{where} is not a SuiteView case bundle (kind={data.get('kind')!r}).")
    version = data.get("schema_version")
    if version not in KNOWN_BUNDLE_VERSIONS:
        known = ", ".join(str(v) for v in KNOWN_BUNDLE_VERSIONS)
        raise CaseBundleError(
            f"Bundle {where} uses schema version {version!r}; this build "
            f"understands version(s) {known}.")
    entries = data.get("cases")
    if not isinstance(entries, list):
        raise CaseBundleError(f"Bundle {where} has no cases array.")
    if not entries:
        raise CaseBundleError(f"Bundle {where} contains no cases.")

    cases: list[SavedCase] = []
    errors: list[tuple[int, str]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append((index, "case entry is not a JSON object"))
            continue
        try:
            cases.append(decode_saved_case(entry))
        except CaseStoreError as exc:
            label = entry.get("name") if isinstance(entry.get("name"), str) else None
            prefix = f"'{label}': " if label else ""
            errors.append((index, f"{prefix}{exc}"))

    return BundleReadResult(
        name=str(data.get("name") or "").strip(),
        cases=cases,
        errors=errors,
        app_version=str(data.get("app_version") or ""),
        exported_at=str(data.get("exported_at") or ""),
        source=source,
    )
