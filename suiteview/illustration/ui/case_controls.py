"""Saved-case controls for the Illustration window.

The Save button in the lookup bar (next to Run Values) drives ``save_flow``;
browsing / loading / copying / renaming / deleting live in the Saved Cases panel
(``saved_cases_panel.py``), which signals the window, which calls back into
this controller. There is no Cases menu anymore.

Persistence lives in ``models/case_store.py``; the inputs payload is
``IllustrationInputsTab.capture_case_inputs()`` and loading applies through
``apply_case_inputs()`` — the same widget surface a Run Values consumes.
Loading is LOUD on mismatch: every input that could not land on the current
policy (missing riders, unavailable premium types, non-IUL allocations…)
is listed in a visible warning — never silently dropped.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
)

from suiteview.illustration.models import case_store
from suiteview.illustration.models.case_store import SavedCase
from suiteview.ui.widgets.frameless_window import FramelessDialog

from .styles import (
    ILLUSTRATION_BORDER_COLOR,
    ILLUSTRATION_HEADER_COLORS,
    PURPLE_BG,
    PURPLE_DARK,
)

_DIALOG_BTN_STYLE = (
    "QPushButton { background-color: #F3ECFC; color: #4B2383;"
    " border: 1px solid #7E57C2; border-radius: 4px; padding: 3px 16px;"
    " font-size: 11px; font-weight: bold; }"
    "QPushButton:hover { background-color: #E8DDF8; }"
)
_DIALOG_EDIT_STYLE = (
    "QLineEdit { background: white; color: #2A1458; border: 1px solid #B79CDE;"
    " border-radius: 3px; padding: 2px 6px; min-height: 20px; font-size: 11px; }"
)


_DATE_STAMP_RE = re.compile(r"\d{2}/\d{2}/\d{4}")


def _date_stamp(when: Optional[date] = None) -> str:
    when = when or date.today()
    return f"{when.month:02d}/{when.day:02d}/{when.year}"


def default_case_name(
    policy_number: str,
    plancode: str = "",
    company_code: str = "",
    when: Optional[date] = None,
) -> str:
    """Fresh-save pre-fill: "CO-POLICY - PLANCODE - mm/dd/yyyy ".

    Company, policy, and plancode keep the flat Saved Cases list
    self-describing (the form number stays out — it's in the row tooltip);
    unknown segments drop out cleanly (no dangling " - "). The trailing
    space is deliberate — the prompt puts the cursor at the end so the user
    just types whatever else they want to add.
    """
    company_code = (company_code or "").strip()
    head = (f"{company_code}-{policy_number}" if company_code
            else str(policy_number))
    parts = [head]
    plancode = (plancode or "").strip()
    if plancode:
        parts.append(plancode)
    parts.append(_date_stamp(when))
    return " - ".join(parts) + " "


def copy_case_default_name(source_name: str,
                           when: Optional[date] = None) -> str:
    """Copy-prompt pre-fill: the source case's name re-stamped to today.

    Any "mm/dd/yyyy" already in the name is replaced with the current date;
    a name with no date gets " - <today>" appended. If that still lands on
    the source's own name (copied the same day), " (copy)" disambiguates so
    the pre-fill never points the copy back at its source file.
    """
    stamp = _date_stamp(when)
    new_name, hits = _DATE_STAMP_RE.subn(stamp, (source_name or "").strip())
    if hits == 0:
        new_name = f"{new_name} - {stamp}"
    if new_name.strip().casefold() == (source_name or "").strip().casefold():
        new_name = f"{new_name} (copy)"
    return new_name


def _name_prompt(parent, title: str, initial: str) -> Optional[str]:
    """Compact framed name-entry dialog; returns the name or None."""
    dlg = FramelessDialog(
        title, parent,
        header_colors=ILLUSTRATION_HEADER_COLORS,
        border_color=ILLUSTRATION_BORDER_COLOR,
        body_color=PURPLE_BG,
    )
    # Wide enough that the pre-filled "CO-POLICY - PLANCODE - mm/dd/yyyy "
    # default plus a typed suffix stays fully visible.
    dlg.setMinimumWidth(560)
    caption = QLabel("Case name")
    caption.setStyleSheet(
        f"color: {PURPLE_DARK}; background: transparent;"
        " font-size: 11px; font-weight: bold;")
    edit = QLineEdit(initial)
    edit.setStyleSheet(_DIALOG_EDIT_STYLE)
    # Cursor at the end, nothing selected — the pre-fill is a prefix the user
    # appends to (default save names end in a trailing space for exactly this).
    edit.setCursorPosition(len(initial))
    dlg.body_layout.addWidget(caption)
    dlg.body_layout.addWidget(edit)
    ok_btn = QPushButton("Save")
    cancel_btn = QPushButton("Cancel")
    for btn in (ok_btn, cancel_btn):
        btn.setStyleSheet(_DIALOG_BTN_STYLE)
    ok_btn.clicked.connect(dlg.accept)
    cancel_btn.clicked.connect(dlg.reject)
    edit.returnPressed.connect(dlg.accept)
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(ok_btn)
    row.addWidget(cancel_btn)
    dlg.body_layout.addLayout(row)
    edit.setFocus()
    if dlg.exec():
        name = edit.text().strip()
        return name or None
    return None


class CasesController:
    """Wires the Save button and the Saved Cases panel to the case store.

    ``window`` is the IllustrationWindow — the controller reads its
    ``_current_key`` (policy, region, company), ``_snapshot_case``,
    ``inputs_tab``, and ``_show_status``. ``directory`` overrides the store
    folder for tests. ``on_cases_changed`` is called after every
    save/rename/delete so case-displaying surfaces (the Saved Cases panel)
    can refresh without the store knowing about the UI.
    """

    def __init__(self, window, directory=None, on_cases_changed=None):
        self._window = window
        self._directory = directory
        self._on_cases_changed = on_cases_changed

    # ── context ───────────────────────────────────────────────

    def _current_key(self) -> Optional[tuple]:
        return getattr(self._window, "_current_key", None)

    def _notify_cases_changed(self):
        if self._on_cases_changed:
            self._on_cases_changed()

    def load_named_case(self, name: str) -> SavedCase:
        """Load a case by name from this controller's store folder (loud)."""
        return case_store.load_case(name, directory=self._directory)

    def delete_named_case(self, name: str) -> None:
        """Delete a case by name (loud) and notify case surfaces."""
        case_store.delete_case(name, directory=self._directory)
        self._notify_cases_changed()

    def rename_named_case(self, old_name: str, new_name: str) -> SavedCase:
        """Rename a case (loud) and notify case surfaces."""
        case = case_store.rename_case(
            old_name, new_name, directory=self._directory)
        self._notify_cases_changed()
        return case

    # ── flows ─────────────────────────────────────────────────

    def save_flow(self):
        """Save the current inputs (and frozen policy data) as a named case.

        The name prompt pre-fills with the loaded saved case's name when a
        snapshot case is active — so a single confirm re-saves/overwrites it
        without a second "overwrite?" question — and with
        "CO-POLICY - PLANCODE - mm/dd/yyyy " for a fresh save otherwise
        (the user appends whatever else they want).
        """
        window = self._window
        key = self._current_key()
        if key is None:
            QMessageBox.information(
                window, "Save Case", "Load a policy before saving a case.")
            return
        policy_number, region, company_code = key
        loaded_case = getattr(window, "_snapshot_case", None)
        # Plancode from the loaded policy data — the frozen snapshot in
        # snapshot mode, the live-loaded data otherwise.
        plancode = getattr(
            getattr(window, "_illustration_data", None), "plancode", "") or ""
        initial = (loaded_case.name if loaded_case is not None
                   else default_case_name(policy_number, plancode,
                                          company_code))
        name = _name_prompt(window, "Save Case", initial)
        if not name:
            return
        try:
            target = case_store.case_path(name, self._directory)
            resaving_loaded = (
                loaded_case is not None
                and target == case_store.case_path(
                    loaded_case.name, self._directory))
            if target.exists() and not resaving_loaded:
                existing = case_store.load_case(name, self._directory)
                answer = QMessageBox.question(
                    window, "Save Case",
                    f"A saved case named '{existing.name}' already exists "
                    f"(policy {existing.policy_number}, saved "
                    f"{existing.saved_at:%m/%d/%Y %H:%M}).\n\nOverwrite it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return
            case = case_store.save_case(
                name,
                policy_number=policy_number,
                region=region,
                company_code=company_code,
                inputs=window.inputs_tab.capture_case_inputs(),
                # Freeze the policy data the case was built against so a later
                # load illustrates the policy as it was NOW, not as it will be.
                # In snapshot mode this is the case's already-frozen data.
                policy_snapshot=getattr(window, "_illustration_data", None),
                overwrite=True,
                directory=self._directory,
            )
        except case_store.CaseStoreError as exc:
            QMessageBox.warning(window, "Save Case", str(exc))
            return
        self._notify_cases_changed()
        window._show_status(
            f"Saved case '{case.name}' for {policy_number} "
            f"({case.path.name}).")

    def copy_flow(self, source_name: str):
        """Duplicate a saved case under a new name.

        The name prompt pre-fills with the source case's name re-stamped to
        today's date (``copy_case_default_name``); the copy gets a fresh
        saved_at while its inputs and frozen snapshot ride through untouched.
        """
        window = self._window
        try:
            source = case_store.load_case(source_name, self._directory)
        except case_store.CaseStoreError as exc:
            QMessageBox.warning(window, "Copy Case", str(exc))
            return
        name = _name_prompt(
            window, "Copy Case", copy_case_default_name(source.name))
        if not name:
            return
        try:
            target = case_store.case_path(name, self._directory)
            if target == source.path:
                QMessageBox.warning(
                    window, "Copy Case",
                    "A copy needs a name different from the source case.")
                return
            if target.exists():
                existing = case_store.load_case(name, self._directory)
                answer = QMessageBox.question(
                    window, "Copy Case",
                    f"A saved case named '{existing.name}' already exists "
                    f"(policy {existing.policy_number}, saved "
                    f"{existing.saved_at:%m/%d/%Y %H:%M}).\n\nOverwrite it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return
            case = case_store.copy_case(
                source_name, name, overwrite=True, directory=self._directory)
        except case_store.CaseStoreError as exc:
            QMessageBox.warning(window, "Copy Case", str(exc))
            return
        self._notify_cases_changed()
        window._show_status(
            f"Copied case '{source.name}' to '{case.name}' "
            f"({case.path.name}).")

    def apply_case(self, case: SavedCase) -> list[str]:
        """Prompt-free apply onto the active inputs tab; returns warnings."""
        return self._window.inputs_tab.apply_case_inputs(case.inputs)
