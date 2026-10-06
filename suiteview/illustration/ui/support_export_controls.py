"""☰ menu "Export Case for Support…" for the Illustration window.

Writes the current case (inputs + frozen policy data) and a support info file
through ``core/support_export.py`` to a folder the user picks (Documents by
default). Reads the window's state only: the loaded key, the policy data, the
inputs tab, the Report tab's last report and the load-time warnings.
"""
from __future__ import annotations

from PyQt6.QtCore import QStandardPaths
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from suiteview.illustration.core.support_export import SupportExportError, write_support_export

EXPORT_FOR_SUPPORT_TEXT = "Export Case for Support…"


def documents_folder() -> str:
    return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)


def add_support_export_action(window, menu) -> QAction:
    """Add the export action to ``menu``; it acts on ``window`` when triggered."""
    action = QAction(EXPORT_FOR_SUPPORT_TEXT, menu)
    action.setToolTip(
        "Save this case (inputs + policy data) and the last run's messages, "
        "warnings and app version for support")
    action.triggered.connect(lambda _checked=False: export_case_for_support(window))
    menu.addAction(action)
    window._support_export_action = action
    return action


def export_case_for_support(window, folder: str | None = None) -> None:
    """Prompt for a folder (unless given) and write the support export loudly."""
    title = "Export Case for Support"
    key = getattr(window, "_current_key", None)
    policy = getattr(window, "_illustration_data", None)
    if key is None or policy is None:
        QMessageBox.information(window, title, "Load a UL policy before exporting a case for support.")
        return
    policy_tab = getattr(window, "policy_tab", None)
    if policy_tab is not None and policy_tab.has_pending_record_changes():
        QMessageBox.warning(
            window, title,
            "Apply or Reset the pending fund/allocation values before exporting a case.")
        return
    if folder is None:
        folder = QFileDialog.getExistingDirectory(window, title, documents_folder())
        if not folder:
            return
    policy_number, region, company_code = key
    checks = getattr(window, "_live_policy_checks", None)
    load_warnings = list(checks[1]) if checks and getattr(window, "_snapshot_case", None) is None else []
    try:
        paths = write_support_export(
            folder,
            policy_number=policy_number,
            region=region,
            company_code=company_code,
            inputs=window.inputs_tab.capture_case_inputs(),
            policy=policy,
            report=window.report_tab.current_report(),
            load_warnings=load_warnings,
        )
    except SupportExportError as exc:
        QMessageBox.warning(window, title, str(exc))
        return
    window._show_status(f"Exported case for support to {paths.case_bundle.parent}.")
    QMessageBox.information(
        window, title,
        f"Saved for support in {paths.case_bundle.parent}:\n\n"
        f"{paths.case_bundle.name}\n{paths.info.name}\n\n"
        "Send both files to support with a note about the number that looks wrong.")
