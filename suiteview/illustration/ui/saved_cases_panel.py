"""Saved Cases view for the Illustration side panel.

One of the two views inside the merged List side window
(``policy_list.py`` hosts it behind a Policies | Saved Cases toggle). It
browses the saved-case store as a FLAT two-column list — no policy grouping:
column 0 is the last-modified date (``mm/dd/yyyy``), column 1 is the case
name, newest first. Clicking a column header sorts (the Saved column sorts
chronologically, not by text). A search bar at the top live-filters the rows
(case-insensitive substring) on the CASE NAME ONLY — deliberately
transparent: what you see in the Case Name column is exactly what the
search matches.

Activating a row asks the window to restore the case (frozen policy snapshot
when present, v1 live-load fallback otherwise). Right-click a case for
Rename / Copy / Delete. Multi-select (Ctrl/Shift-click) is on — the Delete
key or a multi-row right-click ("Delete N Cases…") deletes every selected
case in one batch. The view never writes the store itself — it emits
signals and the window (through CasesController) owns confirmation and
persistence, then calls ``refresh_cases()`` back here.
"""

from datetime import datetime

from PyQt6.QtCore import QByteArray, QMimeData, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QLineEdit,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.models import case_store
from suiteview.illustration.models.case_store import CaseStoreError

from .styles import (
    PURPLE_DARK,
    PURPLE_PRIMARY,
    PURPLE_SUBTLE,
    WHITE,
)

# Custom drag payload for a saved-case row: the case NAME (store slugs are
# per-name, so the name is a unique key). Drop targets — the Compare tab's
# scenario pickers — resolve the case from the store by this name.
SAVED_CASE_MIME = "application/x-suiteview-saved-case"


def format_saved_stamp(saved_at: datetime) -> str:
    """``6/9/2026 3:05 PM`` — platform-safe (no %-flag strftime games)."""
    hour = saved_at.hour % 12 or 12
    meridian = "AM" if saved_at.hour < 12 else "PM"
    return (f"{saved_at.month}/{saved_at.day}/{saved_at.year} "
            f"{hour}:{saved_at.minute:02d} {meridian}")


def format_saved_date(saved_at: datetime) -> str:
    """``06/09/2026`` — the Saved-column date stamp (no time)."""
    return f"{saved_at.month:02d}/{saved_at.day:02d}/{saved_at.year}"


class _CaseRowItem(QTreeWidgetItem):
    """One case row. Sorting the Saved column compares the real ``saved_at``
    timestamp (mm/dd/yyyy text would sort month-first); the Case Name column
    keeps the default text compare."""

    saved_at: datetime

    def __lt__(self, other):
        tree = self.treeWidget()
        if (tree is not None and tree.sortColumn() == 0
                and isinstance(other, _CaseRowItem)):
            return self.saved_at < other.saved_at
        return super().__lt__(other)


class _CaseTreeWidget(QTreeWidget):
    """Case list whose rows can be dragged out onto a drop target.

    A dragged row carries its case name on the custom ``SAVED_CASE_MIME``
    format (plus plain text as a courtesy), so the Compare tab's scenario
    pickers can resolve the saved case from the store on drop. Drag only —
    the view never accepts drops itself. Multi-select is enabled (for batch
    delete) but a drag always resolves to a single row — ``mimeData`` picks
    the first case-row it's handed, which is the pressed/dragged row even
    when several rows are selected."""

    # Delete/Backspace with a selection present — the view translates this
    # into a batch-delete request (see SavedCasesView._on_delete_key_pressed).
    delete_key_pressed = pyqtSignal()

    def mimeData(self, items):
        for item in items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == "case":
                mime = QMimeData()
                mime.setData(SAVED_CASE_MIME, QByteArray(data[1].encode("utf-8")))
                mime.setText(data[1])
                return mime
        return super().mimeData(items)

    def keyPressEvent(self, event):
        if (event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace)
                and self.selectedItems()):
            self.delete_key_pressed.emit()
            return
        super().keyPressEvent(event)


class SavedCasesView(QWidget):
    """Saved-case browser view (search bar + flat date/name case list)."""

    # A saved-case row was activated (case name — store slugs are per-name).
    case_selected = pyqtSignal(str)
    # Right-click → Rename / Copy / Delete on a case row. The window owns the
    # prompt + store write (through CasesController) so this view stays
    # store-write-free.
    case_delete_requested = pyqtSignal(str)
    case_rename_requested = pyqtSignal(str)
    case_copy_requested = pyqtSignal(str)
    # Batch delete — one or more case names, from the Delete key or the
    # multi-row context menu (Rename/Copy stay single-case-only; deleting
    # several at once still routes through this one signal).
    cases_delete_requested = pyqtSignal(list)

    def __init__(self, host_panel=None, parent=None):
        super().__init__(parent)
        # The dockable panel this view lives in — activation is gated on its
        # dock state (same rule as the Policies view's tree).
        self._host = host_panel
        # Read by refresh_cases(); tests point it at a tmp folder. None → the
        # store's default (~/.suiteview/illustration_cases).
        self.cases_directory = None
        self._cases: list = []                   # newest first from the store
        self._cases_error: str | None = None
        # A single-click arms this; a double-click within 220ms cancels the
        # timer and fires immediately instead (avoids a double activation).
        self._pending_case_name: str | None = None
        self._click_timer = QTimer()
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._emit_pending_activation)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Search bar: live-filters on the visible case name only.
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search case name")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {PURPLE_PRIMARY};
                border-radius: 3px;
                padding: 3px 5px;
                font-size: 10px;
                background-color: {WHITE};
            }}
        """)
        self.search_input.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search_input)

        # Flat case list: Saved date | Case name, newest first.
        # Dense, spreadsheet-not-list: compact header, tight rows.
        self.case_tree = _CaseTreeWidget()
        self.case_tree.setColumnCount(2)
        self.case_tree.setHeaderLabels(["Saved", "Case Name"])
        self.case_tree.setRootIsDecorated(False)
        self.case_tree.setIndentation(0)
        self.case_tree.setUniformRowHeights(True)
        self.case_tree.setExpandsOnDoubleClick(False)
        # Rows drag out (onto the Compare tab's scenario pickers); the list
        # never accepts drops itself.
        self.case_tree.setDragEnabled(True)
        self.case_tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        # Ctrl/Shift-click to multi-select for batch delete (Delete key or
        # the "Delete N Cases…" context-menu action).
        self.case_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        header = self.case_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(True)
        # Header-click sorting; the chosen column/order survives refreshes
        # (clear() keeps the sort settings). Default: newest first.
        self.case_tree.setSortingEnabled(True)
        self.case_tree.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        self.case_tree.setStyleSheet(f"""
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
            QHeaderView::section {{
                background-color: {PURPLE_SUBTLE};
                color: {PURPLE_DARK};
                border: none;
                border-bottom: 1px solid {PURPLE_PRIMARY};
                padding: 1px 4px;
                font-size: 8pt;
                font-weight: bold;
            }}
        """)
        self.case_tree.itemClicked.connect(self._on_tree_item_clicked)
        self.case_tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        self.case_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.case_tree.customContextMenuRequested.connect(self._show_context_menu)
        self.case_tree.delete_key_pressed.connect(self._on_delete_key_pressed)
        layout.addWidget(self.case_tree)

        self.refresh_cases()

    # -- Saved cases --------------------------------------------------------

    def refresh_cases(self):
        """Re-read the saved-case store and rebuild the list.

        Called after every save/copy/rename/delete. A corrupt store is
        surfaced as a visible disabled row, never swallowed.
        """
        self._cases_error = None
        try:
            self._cases = case_store.list_cases(directory=self.cases_directory)
        except CaseStoreError as exc:
            self._cases = []
            self._cases_error = str(exc)
        self._rebuild_tree()

    # -- Tree build / filter ------------------------------------------------

    def _rebuild_tree(self):
        self.case_tree.clear()
        if self._cases_error:
            broken = QTreeWidgetItem(
                ["", f"Saved cases unreadable — {self._cases_error}"])
            broken.setFlags(Qt.ItemFlag.NoItemFlags)
            broken.setToolTip(1, self._cases_error)
            self.case_tree.addTopLevelItem(broken)
        for case in self._cases:                 # newest first from the store
            snapshot = case.policy_snapshot
            form = ((snapshot.form_number or "").strip()
                    if snapshot is not None else "")
            item = _CaseRowItem(
                [format_saved_date(case.saved_at), case.name])
            item.saved_at = case.saved_at        # chronological sort key
            item.setData(0, Qt.ItemDataRole.UserRole, ("case", case.name))
            details = [f"Policy: {case.company_code or '—'} - "
                       f"{case.policy_number.strip()}"
                       + (f"  [{form}]" if form else ""),
                       f"Saved: {format_saved_stamp(case.saved_at)}",
                       f"Region: {case.region or '—'}",
                       f"App version: {case.app_version or '—'}"]
            if snapshot is None:
                details.append(
                    "No policy snapshot (saved before snapshots) — "
                    "loads against current policy data.")
            else:
                details.append(
                    "Policy data frozen at save time — loads without DB2.")
            tooltip = "\n".join(details)
            item.setToolTip(0, tooltip)
            item.setToolTip(1, tooltip)
            self.case_tree.addTopLevelItem(item)
        self._apply_filter()

    def _apply_filter(self):
        """Live search (case-insensitive substring) on the visible Case Name
        column ONLY — transparent by design: nothing hidden (policy, form,
        date) ever makes a row match or miss."""
        query = self.search_input.text().strip().lower()
        for i in range(self.case_tree.topLevelItemCount()):
            item = self.case_tree.topLevelItem(i)
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if not data or data[0] != "case":
                continue                       # the store-error row stays put
            item.setHidden(bool(query) and query not in item.text(1).lower())

    # -- Activation ---------------------------------------------------------

    def _activation_allowed(self) -> bool:
        # Same gating as the Policies view: the hosting panel decides
        # (docked, or free-floating while the main window is hidden).
        if self._host is not None:
            return self._host._activation_allowed()
        return True

    @staticmethod
    def _case_name(item) -> str | None:
        data = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        return data[1] if data and data[0] == "case" else None

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int):
        name = self._case_name(item)
        if name is None or not self._activation_allowed():
            return
        # Ctrl/Shift-click extends the selection for a batch delete — don't
        # also queue a case-load activation on top of that.
        modifiers = QApplication.keyboardModifiers()
        if modifiers & (Qt.KeyboardModifier.ControlModifier
                         | Qt.KeyboardModifier.ShiftModifier):
            return
        self._pending_case_name = name
        self._click_timer.start(220)

    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        self._click_timer.stop()
        self._pending_case_name = None
        name = self._case_name(item)
        if name is not None:
            self.case_selected.emit(name)

    def _emit_pending_activation(self):
        name = self._pending_case_name
        self._pending_case_name = None
        if name and self._activation_allowed():
            self.case_selected.emit(name)

    # -- Selection ------------------------------------------------------

    def _selected_case_names(self) -> list[str]:
        """Case names of every currently-selected row, tree order."""
        names = []
        for item in self.case_tree.selectedItems():
            name = self._case_name(item)
            if name is not None:
                names.append(name)
        return names

    def _on_delete_key_pressed(self):
        names = self._selected_case_names()
        if names:
            self.cases_delete_requested.emit(names)

    # -- Context menu -------------------------------------------------------

    def _build_case_menu(self, case_name: str) -> QMenu:
        """Rename / Copy / Delete menu for one case (split for testability)."""
        menu = QMenu(self)
        rename_action = QAction("Rename Case…", self)
        rename_action.triggered.connect(
            lambda checked=False, name=case_name:
                self.case_rename_requested.emit(name))
        menu.addAction(rename_action)
        copy_action = QAction("Copy Case…", self)
        copy_action.triggered.connect(
            lambda checked=False, name=case_name:
                self.case_copy_requested.emit(name))
        menu.addAction(copy_action)
        delete_action = QAction("Delete Case…", self)
        delete_action.triggered.connect(
            lambda checked=False, name=case_name:
                self.case_delete_requested.emit(name))
        menu.addAction(delete_action)
        return menu

    def _build_batch_menu(self, case_names: list[str]) -> QMenu:
        """Delete-only menu for multiple selected cases — Rename/Copy don't
        make sense across more than one case (split for testability)."""
        menu = QMenu(self)
        delete_action = QAction(f"Delete {len(case_names)} Cases…", self)
        delete_action.triggered.connect(
            lambda checked=False, names=list(case_names):
                self.cases_delete_requested.emit(names))
        menu.addAction(delete_action)
        return menu

    def _show_context_menu(self, pos):
        clicked_item = self.case_tree.itemAt(pos)
        clicked_name = self._case_name(clicked_item)
        if clicked_name is None:
            return
        selected_names = self._selected_case_names()
        if clicked_name not in selected_names:
            # Right-click outside the current selection re-anchors it to just
            # the clicked row — standard list/tree UX.
            self.case_tree.clearSelection()
            clicked_item.setSelected(True)
            self.case_tree.setCurrentItem(clicked_item)
            selected_names = [clicked_name]
        if len(selected_names) > 1:
            menu = self._build_batch_menu(selected_names)
        else:
            menu = self._build_case_menu(clicked_name)
        menu.exec(self.case_tree.viewport().mapToGlobal(pos))
