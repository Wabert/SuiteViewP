"""Persistent store for imported illustration case bundles.

Imported cases are kept in their OWN on-disk collection — separate from the
Saved Cases store — so importing files for review or batch work never clutters
the user's permanent saved cases. Each imported FILE is stored as its own
readable ``.cases.json`` bundle under ``~/.suiteview/illustration_imported_cases/``,
which is exactly how the grouping is preserved: one stored bundle == one node in
the Imported Cases tree. A multi-case bundle expands to its cases; a single-case
bundle shows the case name directly.

The store never prompts. Duplicate resolution (overwrite vs. rename) is the
caller's decision — the store simply refuses to clobber an existing bundle
unless ``overwrite`` is set. Writes go through the atomic bundle writer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from suiteview.illustration.models.case_bundle import (
    BUNDLE_SUFFIX,
    CaseBundleError,
    read_bundle,
    write_bundle,
)
from suiteview.illustration.models.case_store import SavedCase


class ImportedCaseError(Exception):
    """An imported bundle cannot be persisted, read, or resolved."""


class ImportedBundleExistsError(ImportedCaseError):
    """A stored bundle of this name already exists (overwrite not permitted)."""


@dataclass
class ImportedBundle:
    """One imported bundle as stored on disk (one node in the tree)."""

    display_name: str
    path: Path
    cases: list[SavedCase]

    @property
    def is_single(self) -> bool:
        return len(self.cases) == 1

    @property
    def node_label(self) -> str:
        """What the tree shows for this bundle's top node: the single case's
        name when it holds exactly one, else the bundle's own display name."""
        if self.is_single:
            return self.cases[0].name
        return self.display_name


def default_imported_dir() -> Path:
    return Path.home() / ".suiteview" / "illustration_imported_cases"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip()).strip("._-")
    if not slug:
        raise ImportedCaseError(
            f"Bundle name {name!r} must contain at least one letter or digit.")
    return slug.lower()


def imported_bundle_path(display_name: str, directory: Optional[Path] = None) -> Path:
    """The file a stored bundle of this display name lives in."""
    directory = Path(directory) if directory else default_imported_dir()
    return directory / f"{_slugify(display_name)}{BUNDLE_SUFFIX}"


def bundle_exists(display_name: str, directory: Optional[Path] = None) -> bool:
    return imported_bundle_path(display_name, directory).exists()


def unique_display_name(display_name: str, directory: Optional[Path] = None) -> str:
    """A display name whose stored file does not yet exist — appends
    ``(2)``, ``(3)``… until free. Used to pre-fill the Rename choice."""
    base = str(display_name or "").strip() or "Imported cases"
    candidate = base
    counter = 2
    while bundle_exists(candidate, directory):
        candidate = f"{base} ({counter})"
        counter += 1
    return candidate


def save_imported_bundle(
    display_name: str,
    cases: list[SavedCase],
    *,
    overwrite: bool = False,
    directory: Optional[Path] = None,
) -> ImportedBundle:
    """Persist selected cases as a stored bundle node.

    Raises ImportedBundleExistsError when a bundle of this name already exists
    and ``overwrite`` is False — the caller decides overwrite vs. rename.
    """
    if not cases:
        raise ImportedCaseError("Cannot store a bundle with no cases.")
    path = imported_bundle_path(display_name, directory)
    if path.exists() and not overwrite:
        raise ImportedBundleExistsError(
            f"An imported bundle named '{display_name}' already exists.")
    try:
        write_bundle(path, cases, name=str(display_name or "").strip())
    except CaseBundleError as exc:
        raise ImportedCaseError(str(exc)) from exc
    return ImportedBundle(
        display_name=str(display_name or "").strip(), path=path, cases=list(cases))


def _read_stored_bundle(path: Path) -> ImportedBundle:
    try:
        result = read_bundle(path)
    except CaseBundleError as exc:
        raise ImportedCaseError(f"Imported bundle {path} is unreadable: {exc}") from exc
    if result.errors:
        # The store only ever writes fully-valid bundles, so a stored bundle
        # that no longer decodes cleanly is corruption — surface it loudly.
        first = result.errors[0][1]
        raise ImportedCaseError(
            f"Imported bundle {path} contains an unreadable case: {first}")
    display = result.name or path.name[: -len(BUNDLE_SUFFIX)]
    return ImportedBundle(display_name=display, path=path, cases=result.cases)


def list_imported_bundles(directory: Optional[Path] = None) -> list[ImportedBundle]:
    """All stored imported bundles, newest first. A corrupt stored bundle
    raises (naming the file) rather than being silently skipped."""
    folder = Path(directory) if directory else default_imported_dir()
    if not folder.is_dir():
        return []
    paths = sorted(folder.glob(f"*{BUNDLE_SUFFIX}"))
    bundles = [_read_stored_bundle(path) for path in paths]
    bundles.sort(key=lambda b: b.path.stat().st_mtime, reverse=True)
    return bundles


def load_imported_case(bundle_path: Path | str, case_name: str) -> SavedCase:
    """Load one case by name from a stored bundle (loud on missing)."""
    bundle = _read_stored_bundle(Path(bundle_path))
    for case in bundle.cases:
        if case.name == case_name:
            return case
    raise ImportedCaseError(
        f"No imported case named '{case_name}' in {Path(bundle_path).name}.")


def remove_imported_bundle(bundle_path: Path | str) -> None:
    """Delete an entire stored bundle node."""
    path = Path(bundle_path)
    if not path.exists():
        raise ImportedCaseError(f"No imported bundle at {path}.")
    path.unlink()


def remove_imported_cases(
    bundle_path: Path | str,
    case_names: list[str],
) -> Optional[ImportedBundle]:
    """Remove one or more cases from a stored bundle.

    Rewrites the bundle without those cases; if none remain, the file is
    deleted and ``None`` is returned. Otherwise the rewritten bundle is
    returned.
    """
    path = Path(bundle_path)
    bundle = _read_stored_bundle(path)
    drop = set(case_names)
    kept = [case for case in bundle.cases if case.name not in drop]
    if len(kept) == len(bundle.cases):
        raise ImportedCaseError(
            f"None of {case_names} are in imported bundle {path.name}.")
    if not kept:
        path.unlink()
        return None
    write_bundle(path, kept, name=bundle.display_name)
    return ImportedBundle(display_name=bundle.display_name, path=path, cases=kept)
