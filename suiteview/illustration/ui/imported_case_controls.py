"""Imported-case controls for the Illustration window.

The Imported Cases view (``imported_cases_panel.py``) is store-write-free: it
emits intent, and this controller owns the file dialogs, the duplicate and
validation prompts, and the writes into the imported-case store
(``models/imported_case_store.py``). After every change it calls
``on_changed`` so the view refreshes.

Import is granular and loud: a malformed bundle envelope is rejected with a
message; a bundle whose cases are a mix of valid and invalid lets the user
import the valid subset, accept the file anyway (same valid subset), or refuse
it. Duplicates (a stored bundle of the same name) offer Overwrite or Rename.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QMessageBox

from suiteview.illustration.models import case_bundle, imported_case_store
from suiteview.illustration.models.case_bundle import CaseBundleError
from suiteview.illustration.models.imported_case_store import ImportedCaseError


def _default_display_name(result, source: Path) -> str:
    """The bundle's own name if it set one, else the source file's stem
    (``foo.cases.json`` → ``foo``)."""
    if result.name:
        return result.name
    stem = source.name
    if stem.lower().endswith(case_bundle.BUNDLE_SUFFIX):
        stem = stem[: -len(case_bundle.BUNDLE_SUFFIX)]
    elif stem.lower().endswith(".json"):
        stem = stem[:-5]
    return stem or "Imported cases"


class ImportedCasesController:
    """Wires the Imported Cases view to the imported-case store."""

    def __init__(self, window, directory=None, on_changed=None):
        self._window = window
        self._directory = directory
        self._on_changed = on_changed

    def _notify(self):
        if self._on_changed:
            self._on_changed()

    # ── import ────────────────────────────────────────────────

    def pick_and_import(self):
        """Open a multi-select file picker and import the chosen bundles."""
        paths, _ = QFileDialog.getOpenFileNames(
            self._window, "Import Cases", "",
            f"Case bundle (*{case_bundle.BUNDLE_SUFFIX});;JSON (*.json)")
        if paths:
            self.import_files(paths)

    def import_files(self, paths: list[str]):
        """Import each dropped/picked bundle file. Errors are per-file — one
        bad file never aborts the others."""
        imported = 0
        for path in paths:
            if self._import_one(Path(path)):
                imported += 1
        if imported:
            self._notify()
            self._window._show_status(
                f"Imported {imported} case file{'s' if imported != 1 else ''}.")

    def _import_one(self, source: Path) -> bool:
        window = self._window
        try:
            result = case_bundle.read_bundle(source)
        except CaseBundleError as exc:
            QMessageBox.warning(window, "Import Cases", str(exc))
            return False

        cases = result.cases
        if result.has_errors:
            cases = self._resolve_mixed(source, result)
            if cases is None:          # user refused the whole file
                return False
        if not cases:
            QMessageBox.warning(
                window, "Import Cases",
                f"{source.name} has no importable cases.")
            return False

        display_name = _default_display_name(result, source)
        return self._store_with_conflict(display_name, cases)

    def _resolve_mixed(self, source: Path, result):
        """Prompt for a bundle with both valid and invalid cases. Returns the
        cases to store, or None to skip the file entirely."""
        detail = "\n".join(
            f"•  case #{index + 1}: {message}"
            for index, message in result.errors[:8])
        if len(result.errors) > 8:
            detail += f"\n•  … and {len(result.errors) - 8} more"
        box = QMessageBox(self._window)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Import Cases")
        box.setText(
            f"{source.name} has {len(result.cases)} valid case(s) and "
            f"{len(result.errors)} that could not be read.")
        box.setInformativeText(detail)
        import_valid = box.addButton(
            f"Import Valid ({len(result.cases)})",
            QMessageBox.ButtonRole.AcceptRole)
        accept_all = box.addButton("Accept Anyway", QMessageBox.ButtonRole.YesRole)
        box.addButton("Refuse File", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked in (import_valid, accept_all):
            # Both bring in the valid subset — invalid entries cannot be
            # materialized, so "accept anyway" simply proceeds without nagging.
            return result.cases
        return None

    def _store_with_conflict(self, display_name: str, cases) -> bool:
        """Persist cases as an imported bundle, resolving a name collision by
        Overwrite or Rename."""
        window = self._window
        if imported_case_store.bundle_exists(display_name, self._directory):
            box = QMessageBox(window)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle("Import Cases")
            box.setText(
                f"An imported bundle named '{display_name}' already exists.")
            box.setInformativeText("Overwrite it, or import as a renamed copy?")
            overwrite = box.addButton("Overwrite", QMessageBox.ButtonRole.YesRole)
            rename = box.addButton("Rename", QMessageBox.ButtonRole.NoRole)
            box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is overwrite:
                return self._save(display_name, cases, overwrite=True)
            if clicked is rename:
                unique = imported_case_store.unique_display_name(
                    display_name, self._directory)
                return self._save(unique, cases, overwrite=False)
            return False
        return self._save(display_name, cases, overwrite=False)

    def _save(self, display_name: str, cases, *, overwrite: bool) -> bool:
        try:
            imported_case_store.save_imported_bundle(
                display_name, cases, overwrite=overwrite,
                directory=self._directory)
        except ImportedCaseError as exc:
            QMessageBox.warning(self._window, "Import Cases", str(exc))
            return False
        return True

    # ── activation ────────────────────────────────────────────

    def activate_case(self, bundle_path: str, case_name: str):
        try:
            case = imported_case_store.load_imported_case(bundle_path, case_name)
        except ImportedCaseError as exc:
            QMessageBox.warning(self._window, "Load Case", str(exc))
            return
        self._window._activate_case(case)

    # ── remove ────────────────────────────────────────────────

    def remove_cases(self, items: list):
        """Remove selected imported cases (list of (bundle_path, case_name))."""
        if not items:
            return
        count = len(items)
        answer = QMessageBox.question(
            self._window, "Remove Imported Cases",
            f"Remove {count} imported case{'s' if count != 1 else ''} "
            f"from the list?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        by_bundle: dict[str, list[str]] = {}
        for bundle_path, case_name in items:
            by_bundle.setdefault(bundle_path, []).append(case_name)
        try:
            for bundle_path, names in by_bundle.items():
                imported_case_store.remove_imported_cases(bundle_path, names)
        except ImportedCaseError as exc:
            QMessageBox.warning(self._window, "Remove Imported Cases", str(exc))
        self._notify()
        self._window._show_status(
            f"Removed {count} imported case{'s' if count != 1 else ''}.")

    def remove_bundles(self, bundle_paths: list):
        """Remove selected imported bundles entirely (list of bundle_path)."""
        if not bundle_paths:
            return
        count = len(bundle_paths)
        answer = QMessageBox.question(
            self._window, "Remove Imported Bundles",
            f"Remove {count} imported file{'s' if count != 1 else ''} "
            f"and all their cases?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            for bundle_path in bundle_paths:
                imported_case_store.remove_imported_bundle(bundle_path)
        except ImportedCaseError as exc:
            QMessageBox.warning(self._window, "Remove Imported Bundles", str(exc))
        self._notify()
        self._window._show_status(
            f"Removed {count} imported file{'s' if count != 1 else ''}.")

    # ── export ────────────────────────────────────────────────

    def export_cases(self, items: list):
        """Export selected imported cases (list of (bundle_path, case_name)) to
        one readable ``.cases.json`` bundle."""
        window = self._window
        if not items:
            return
        # De-dup while preserving order (a case may appear once).
        seen = set()
        cases = []
        try:
            for bundle_path, case_name in items:
                key = (bundle_path, case_name)
                if key in seen:
                    continue
                seen.add(key)
                cases.append(imported_case_store.load_imported_case(
                    bundle_path, case_name))
        except ImportedCaseError as exc:
            QMessageBox.warning(window, "Export Cases", str(exc))
            return
        if not cases:
            return
        default_name = case_bundle.default_bundle_name(cases)
        suggested = f"{_export_slug(default_name)}{case_bundle.BUNDLE_SUFFIX}"
        path, _ = QFileDialog.getSaveFileName(
            window, "Export Cases", suggested,
            f"Case bundle (*{case_bundle.BUNDLE_SUFFIX})")
        if not path:
            return
        try:
            written = case_bundle.write_bundle(path, cases, name=default_name)
        except CaseBundleError as exc:
            QMessageBox.warning(window, "Export Cases", str(exc))
            return
        count = len(cases)
        window._show_status(
            f"Exported {count} case{'s' if count != 1 else ''} to "
            f"{written.name}.")


def _export_slug(name: str) -> str:
    import re

    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip()).strip("._-")
    return slug or "cases"
