"""Imported Cases view for the Illustration side panel.

The third view inside the List side window (``policy_list.py`` hosts it behind a
Policies | Saved Cases | Imported Cases toggle). It browses the separate
imported-case store, GROUPED BY SOURCE FILE: each stored ``.cases.json`` bundle
is one node. A bundle holding several cases shows as an expandable parent (its
file/bundle name) with a child row per case; a single-case bundle shows the case
name directly as the top node.

An Import button opens a file picker; dropping ``.cases.json`` files anywhere on
the List panel routes here too. Double-clicking a case loads it into the Inputs
tab (frozen snapshot, exactly like a Saved Case). Right-click offers Load,
Export, and Remove. The view never writes the store itself — it emits signals
and the window (through ImportedCasesController) owns the file dialogs,
confirmation, and persistence, then calls ``refresh()`` back here.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.models import imported_case_store
from suiteview.illustration.models.imported_case_store import ImportedCaseError

from .styles import (
    GOLD_PRIMARY,
    GOLD_TEXT,
    PURPLE_DARK,
    PURPLE_PRIMARY,
    PURPLE_RICH,
    PURPLE_SUBTLE,
    WHITE,
)

# UserRole payloads. A case row: ("case", bundle_path, case_name). A bundle
# parent row (multi-case only): ("bundle", bundle_path, None).
_ROLE = Qt.ItemDataRole.UserRole


class _ImportedTreeWidget(QTreeWidget):
    """Imported-case tree with Delete/Backspace wired to a remove request."""

    delete_key_pressed = pyqtSignal()

    def keyPressEvent(self, event):
        if (event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace)
                and self.selectedItems()):
            self.delete_key_pressed.emit()
            return
        super().keyPressEvent(event)


class ImportedCasesView(QWidget):
    """Imported-case browser: an Import button over a file-grouped case tree."""

    # The Import button was clicked — the window opens a multi-select file
    # picker and imports the chosen bundles.
    import_requested = pyqtSignal()
    # A case row was activated (bundle path, case name) — load its snapshot.
    case_activated = pyqtSignal(str, str)
    # Remove requests. Cases: a list of (bundle_path, case_name). Bundles: a
    # list of bundle_path. The window confirms and writes through the store.
    cases_remove_requested = pyqtSignal(list)
    bundles_remove_requested = pyqtSignal(list)
    # Export selected imported cases to one bundle: list of (bundle_path,
    # case_name).
    cases_export_requested = pyqtSignal(list)

    def __init__(self, host_panel=None, parent=None):
        super().__init__(parent)
        self._host = host_panel
        # Read by refresh(); tests point it at a tmp folder. None → the store's
        # default (~/.suiteview/data/illustration/imported_cases).
        self.imported_directory = None
        self._bundles: list = []
        self._error: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        button_row = QHBoxLayout()
        button_row.setSpacing(4)
        self.import_btn = QPushButton("Import…")
        self.import_btn.setToolTip(
            "Import one or more .cases.json files into the imported list")
        self.import_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {PURPLE_PRIMARY};
                color: {GOLD_TEXT};
                border: 1px solid {GOLD_PRIMARY};
                border-radius: 3px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 10px;
            }}
            QPushButton:hover {{ background-color: {PURPLE_RICH}; }}
        """)
        self.import_btn.clicked.connect(self.import_requested.emit)
        button_row.addWidget(self.import_btn)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        # File-grouped case tree. Unlike the flat Saved Cases list, this one
        # shows expand arrows + indentation so a bundle's cases nest under it.
        self.tree = _ImportedTreeWidget()
        self.tree.setColumnCount(1)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(12)
        self.tree.setUniformRowHeights(True)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {WHITE};
                border: 1px solid {PURPLE_PRIMARY};
                border-radius: 3px;
                font-family: 'Segoe UI';
                font-size: 9pt;
            }}
            QTreeWidget::item {{
                padding: 0px 4px;
                margin: 0px;
                min-height: 18px;
                max-height: 18px;
            }}
            QTreeWidget::item:selected {{
                background-color: #FFE8A3;
                color: {PURPLE_DARK};
            }}
            QTreeWidget::item:hover {{
                background-color: {PURPLE_SUBTLE};
            }}
        """)
        self.tree.itemDoubleClicked.connect(self._on_double_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.delete_key_pressed.connect(self._on_delete_key_pressed)
        layout.addWidget(self.tree)

        self.refresh()

    # -- refresh / build ----------------------------------------------------

    def refresh(self):
        """Re-read the imported-case store and rebuild the tree."""
        self._error = None
        try:
            self._bundles = imported_case_store.list_imported_bundles(
                directory=self.imported_directory)
        except ImportedCaseError as exc:
            self._bundles = []
            self._error = str(exc)
        self._rebuild()

    def _rebuild(self):
        self.tree.clear()
        if self._error:
            broken = QTreeWidgetItem([f"Imported cases unreadable — {self._error}"])
            broken.setFlags(Qt.ItemFlag.NoItemFlags)
            broken.setToolTip(0, self._error)
            self.tree.addTopLevelItem(broken)
            return
        for bundle in self._bundles:
            path = str(bundle.path)
            if bundle.is_single:
                case = bundle.cases[0]
                item = QTreeWidgetItem([case.name])
                item.setData(0, _ROLE, ("case", path, case.name))
                item.setToolTip(0, self._case_tooltip(bundle, case))
                self.tree.addTopLevelItem(item)
            else:
                parent = QTreeWidgetItem(
                    [f"{bundle.display_name}  ({len(bundle.cases)})"])
                parent.setData(0, _ROLE, ("bundle", path, None))
                parent.setToolTip(
                    0, f"{bundle.path.name} — {len(bundle.cases)} cases")
                self.tree.addTopLevelItem(parent)
                for case in bundle.cases:
                    child = QTreeWidgetItem([case.name])
                    child.setData(0, _ROLE, ("case", path, case.name))
                    child.setToolTip(0, self._case_tooltip(bundle, case))
                    parent.addChild(child)
                parent.setExpanded(True)

    @staticmethod
    def _case_tooltip(bundle, case) -> str:
        lines = [
            f"Case: {case.name}",
            f"Policy: {case.company_code or '—'} - {case.policy_number.strip()}",
            f"Region: {case.region or '—'}",
            f"From file: {bundle.path.name}",
        ]
        if case.policy_snapshot is None:
            lines.append("No policy snapshot — loads against current policy data.")
        else:
            lines.append("Policy data frozen at save time — loads without DB2.")
        return "\n".join(lines)

    # -- selection helpers --------------------------------------------------

    @staticmethod
    def _payload(item):
        return item.data(0, _ROLE) if item else None

    def _selected_cases(self) -> list[tuple[str, str]]:
        """(bundle_path, case_name) for every selected case row."""
        out = []
        for item in self.tree.selectedItems():
            data = self._payload(item)
            if data and data[0] == "case":
                out.append((data[1], data[2]))
        return out

    def _selected_bundles(self) -> list[str]:
        """bundle_path for every selected bundle parent row."""
        out = []
        for item in self.tree.selectedItems():
            data = self._payload(item)
            if data and data[0] == "bundle":
                out.append(data[1])
        return out

    # -- activation ---------------------------------------------------------

    def _activation_allowed(self) -> bool:
        if self._host is not None:
            return self._host._activation_allowed()
        return True

    def _on_double_clicked(self, item: QTreeWidgetItem, column: int):
        data = self._payload(item)
        if not data:
            return
        if data[0] == "case" and self._activation_allowed():
            self.case_activated.emit(data[1], data[2])
        elif data[0] == "bundle":
            item.setExpanded(not item.isExpanded())

    # -- remove -------------------------------------------------------------

    def _on_delete_key_pressed(self):
        self._emit_remove(self._selected_cases(), self._selected_bundles())

    def _emit_remove(self, cases: list, bundles: list):
        if bundles:
            self.bundles_remove_requested.emit(bundles)
        if cases:
            self.cases_remove_requested.emit(cases)

    # -- context menu -------------------------------------------------------

    def _show_context_menu(self, pos):
        clicked = self.tree.itemAt(pos)
        data = self._payload(clicked)
        if not data:
            return
        # Re-anchor selection to the clicked row if it is outside the current
        # selection (standard tree UX), so the menu acts on what was clicked.
        if not clicked.isSelected():
            self.tree.clearSelection()
            clicked.setSelected(True)
            self.tree.setCurrentItem(clicked)

        cases = self._selected_cases()
        bundles = self._selected_bundles()
        menu = QMenu(self)

        if data[0] == "case" and len(cases) == 1 and not bundles:
            bundle_path, case_name = cases[0]
            load = QAction("Load Case", self)
            load.triggered.connect(
                lambda checked=False, p=bundle_path, n=case_name:
                    self.case_activated.emit(p, n))
            menu.addAction(load)
            export = QAction("Export Case…", self)
            export.triggered.connect(
                lambda checked=False, items=list(cases):
                    self.cases_export_requested.emit(items))
            menu.addAction(export)
            remove = QAction("Remove", self)
            remove.triggered.connect(
                lambda checked=False, items=list(cases):
                    self.cases_remove_requested.emit(items))
            menu.addAction(remove)
        elif data[0] == "bundle" and len(bundles) == 1 and not cases:
            bundle_path = bundles[0]
            export = QAction("Export Bundle…", self)
            export.triggered.connect(
                lambda checked=False, p=bundle_path:
                    self.cases_export_requested.emit(self._bundle_case_items(p)))
            menu.addAction(export)
            remove = QAction("Remove Bundle", self)
            remove.triggered.connect(
                lambda checked=False, items=[bundle_path]:
                    self.bundles_remove_requested.emit(items))
            menu.addAction(remove)
        else:
            total = len(cases) + len(bundles)
            if total == 0:
                return
            export = QAction(f"Export {total} Selected…", self)
            export.triggered.connect(
                lambda checked=False, c=list(cases), b=list(bundles):
                    self.cases_export_requested.emit(
                        c + self._bundles_case_items(b)))
            menu.addAction(export)
            remove = QAction(f"Remove {total} Selected", self)
            remove.triggered.connect(
                lambda checked=False, c=list(cases), b=list(bundles):
                    self._emit_remove(c, b))
            menu.addAction(remove)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _bundle_case_items(self, bundle_path: str) -> list[tuple[str, str]]:
        for bundle in self._bundles:
            if str(bundle.path) == bundle_path:
                return [(bundle_path, case.name) for case in bundle.cases]
        return []

    def _bundles_case_items(self, bundle_paths: list) -> list[tuple[str, str]]:
        out = []
        for path in bundle_paths:
            out.extend(self._bundle_case_items(path))
        return out
