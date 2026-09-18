"""Compact ADMIN-only access editor; all persistence belongs to the repository."""

from __future__ import annotations

import logging

import pandas as pd
from PyQt6.QtCore import QSignalBlocker, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from suiteview.administrator.service import (
    APP_CODES, AccessRepository, AccessRole, AccessUser,
)
from suiteview.audit.tabs._styles import make_checkbox
from suiteview.core.build_env import has_developer_access
from suiteview.polview.ui.widgets import StyledInfoTableGroup
from suiteview.ui.widgets.filter_table_view import FilterTableView
from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from suiteview.ui.widgets.uppercase_input import force_uppercase

logger = logging.getLogger(__name__)


class AdministratorWindow(FramelessWindowBase):
    """One selected identity per editor, independent of displayed row positions."""

    permissions_changed = pyqtSignal()

    def __init__(self, repository=None, parent=None):
        self.repository = repository if repository is not None else AccessRepository()
        # Do not construct even an empty sensitive widget tree before authorization.
        self.snapshot = self.repository.load()
        self._loading = True
        self._blocked = False
        self._tab = 0
        self._originals = [None, None]
        self._baselines = [None, None]
        self._new = [False, False]
        super().__init__(
            title="Administrator", default_size=(1040, 660),
            min_size=(940, 620), parent=parent,
        )
        self._populate()
        self._loading = False
        self._update_dirty()

    def build_content(self):
        body = QWidget()
        body.setObjectName("administratorBody")
        body.setStyleSheet("""
            QWidget#administratorBody { background: #F4F7FB; color: #173659; }
            QLineEdit, QComboBox { background: white; border: 1px solid #A8BAD0;
                padding: 2px 4px; min-height: 20px; }
            QPushButton { color: #173659; background: #EDF2F9;
                border: 1px solid #9FB5CF; border-radius: 3px; padding: 4px 12px; }
            QPushButton:hover { background: #DDE9F8; }
            QPushButton:disabled { color: #8C929A; background: #E9EBEE; }
            QTabBar::tab { padding: 5px 16px; }
            QTabBar::tab:selected { color: #0D3A7A; border-bottom: 2px solid #D4A017; }
        """)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)
        toolbar = QHBoxLayout()
        self.status = QLabel()
        self._set_status()
        self.status.setWordWrap(True)
        toolbar.addWidget(self.status, 1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_button)
        layout.addLayout(toolbar)
        self.enforcement_notice = QLabel(
            "Runtime permissions: packaged SuiteView checks enabled users and app access on entry, "
            "and write permissions before database or policy-support changes. "
            "Source developer runs remain unrestricted."
        )
        self.enforcement_notice.setWordWrap(True)
        self.enforcement_notice.setStyleSheet(
            "background: #FFF7DE; color: #594614; border: 1px solid #D4A017;"
            "border-radius: 3px; padding: 5px 8px; font-size: 11px;"
        )
        layout.addWidget(self.enforcement_notice)
        self.tabs = QTabWidget()
        self.tables = []
        self.editors = []
        self.save_buttons = []
        self.delete_buttons = []
        for index, title in enumerate(("Users", "Roles & Apps")):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(4, 6, 4, 0)
            split = QSplitter(Qt.Orientation.Horizontal)
            table = FilterTableView()
            table.apply_ledger_style(
                header_bg="#E7EEF8", header_fg="#173659", border="#BACADF",
                selection_bg="#DDE9F8", selection_fg="#173659",
            )
            table.export_btn.setStyleSheet(
                "background: #E7EEF8; color: #173659; border: 1px solid #9FB5CF;"
                "border-radius: 3px; padding: 4px 8px;"
            )
            table.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.table_view.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            table.table_view.verticalHeader().setMinimumSectionSize(16)
            table.table_view.verticalHeader().setDefaultSectionSize(16)
            table.header.setFixedHeight(18)
            table.table_view.setStyleSheet(
                table.table_view.styleSheet() + "\nQTableView#filterTableView::item { padding: 0px; }"
            )
            self.tables.append(table)
            split.addWidget(table)
            detail = QWidget()
            detail.setMinimumWidth(365)
            detail_layout = QVBoxLayout(detail)
            detail_layout.setContentsMargins(6, 0, 0, 0)
            detail_layout.setSpacing(6)
            editor = self._build_user_editor() if index == 0 else self._build_role_editor()
            self.editors.append(editor)
            detail_layout.addWidget(editor, 1)
            buttons = QHBoxLayout()
            for text, callback in (
                ("New", self.new_record), ("Save", self.save_record),
                ("Delete", self.delete_record),
            ):
                button = QPushButton(text)
                button.clicked.connect(callback)
                buttons.addWidget(button)
                if text == "Save":
                    self.save_buttons.append(button)
                elif text == "Delete":
                    self.delete_buttons.append(button)
            detail_layout.addLayout(buttons)
            split.addWidget(detail)
            split.setSizes([625, 385])
            split.setCollapsible(0, False)
            split.setCollapsible(1, False)
            page_layout.addWidget(split)
            self.tabs.addTab(page, title)
        self.tabs.currentChanged.connect(self._change_tab)
        layout.addWidget(self.tabs, 1)
        return body

    def _field(self, group, label, key, widget):
        group.add_field(label, key, label_width=132, value_width=170)
        group._labels[key].setStyleSheet(
            "color: #173659; font-size: 11px; font-weight: bold; background: transparent;"
        )
        widget.setMinimumWidth(170)
        group.set_field_editor(key, widget)
        if isinstance(widget, QLineEdit):
            widget.textChanged.connect(self._update_dirty)
            widget.textChanged.connect(widget.setToolTip)
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(self._update_dirty)
        else:
            widget.toggled.connect(self._update_dirty)
        return widget

    @staticmethod
    def _info_group(title):
        group = StyledInfoTableGroup(title, show_table=False)
        group.setStyleSheet("""
            QGroupBox { background: white; border: 1px solid #9FB5CF;
                border-radius: 5px; margin-top: 8px; font-weight: bold; color: #173659; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px;
                background: #0D3A7A; color: #F3D47A; padding: 2px 8px;
                border-radius: 3px; }
        """)
        group._info_layout.setColumnStretch(1, 1)
        group._info_layout.setColumnStretch(2, 0)
        return group

    def _build_user_editor(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        group = self._info_group("User details")
        self.user_id = self._field(group, "Network ID", "network_id", QLineEdit())
        self.user_name = self._field(group, "Name", "name", QLineEdit())
        self.user_enabled = self._field(group, "Enabled", "enabled", make_checkbox(""))
        self.user_role = self._field(group, "Role", "role", QComboBox())
        force_uppercase(self.user_id)
        self.user_id.setMaxLength(50)
        self.user_name.setMaxLength(200)
        note = QLabel("One role per user. Network ID is fixed after creation.\n"
                      "Enabled status is enforced across packaged SuiteView.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #64748B; font-size: 11px;")
        group.layout().addWidget(note)
        layout.addWidget(group)
        layout.addStretch(1)
        return panel

    def _build_role_editor(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        group = self._info_group("Role details")
        self.role_code = self._field(group, "Role code", "role_code", QLineEdit())
        self.role_description = self._field(group, "Description", "description", QLineEdit())
        self.role_all_apps = self._field(group, "AllApps", "all_apps", make_checkbox(""))
        self.role_update = self._field(group, "CanUpdateDatabase", "update", make_checkbox(""))
        self.role_support = self._field(group, "CanWriteSupportFiles", "support", make_checkbox(""))
        group.add_field("Assigned users", "affected", label_width=132, value_width=170)
        group._labels["affected"].setStyleSheet(
            "color: #173659; font-size: 11px; font-weight: bold; background: transparent;"
        )
        self.role_group = group
        force_uppercase(self.role_code)
        self.role_code.setMaxLength(50)
        self.role_description.setMaxLength(200)
        self.role_all_apps.toggled.connect(self._update_picker)
        layout.addWidget(group)
        self.app_note = QLabel()
        self.app_note.setWordWrap(True)
        layout.addWidget(self.app_note)
        self.app_scroll = QScrollArea()
        self.app_scroll.setWidgetResizable(True)
        self.app_scroll.setMinimumHeight(190)
        self.app_picker = QWidget()
        self.app_grid = QGridLayout(self.app_picker)
        self.app_grid.setContentsMargins(6, 6, 6, 6)
        self.app_grid.setHorizontalSpacing(8)
        self.app_grid.setVerticalSpacing(2)
        self.app_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.app_checks = {}
        self.app_scroll.setWidget(self.app_picker)
        layout.addWidget(self.app_scroll, 1)
        admin_note = QLabel("Packaged Administrator requires role ADMIN.\n"
                            "It cannot be granted by AllApps or an app whitelist.")
        admin_note.setWordWrap(True)
        admin_note.setStyleSheet("color: #64748B; font-size: 11px;")
        layout.addWidget(admin_note)
        return panel

    def _populate(self, preferred=None):
        self._loading = True
        self.user_role.clear()
        for role in self.snapshot.roles:
            self.user_role.addItem(role.role_code, role.role_code)
        datasets = (
            ([(u.network_id, u.name, "Yes" if u.enabled else "No", u.role_code)
              for u in self.snapshot.users], ["Network ID", "Name", "Enabled", "Role"]),
            ([(r.role_code, r.description, self._affected(r.role_code))
              for r in self.snapshot.roles], ["Role", "Description", "Users"]),
        )
        for index, (rows, columns) in enumerate(datasets):
            table = self.tables[index]
            table.set_dataframe(pd.DataFrame(rows, columns=columns), limit_rows=False)
            table.model._left_align_columns = {0, 1, 3} if index == 0 else {0, 1}
            table.autofit_columns_to_data()
            metrics = QFontMetrics(table.header.wrap_font())
            for column, label in enumerate(columns):
                # A fixed 18px header must fit the whole label on one line.
                width = metrics.horizontalAdvance(label) + table.header.sort_icon_width + 12
                table.table_view.setColumnWidth(
                    column, max(table.table_view.columnWidth(column), width)
                )
            table.header.setFixedHeight(18)
            table.header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            table.table_view.selectionModel().currentRowChanged.connect(
                lambda current, previous, i=index: self._select_row(i, current)
            )
            # FilterTableView resets its model for both sorting and filtering.
            # Retain the editor identity even when its row is filtered out.
            table.model.modelReset.connect(lambda i=index: self._restore_selection(i))
            records = self.snapshot.users if index == 0 else self.snapshot.roles
            key = preferred[index] if preferred else None
            record = next((r for r in records if self._key(r) == key), None)
            self._show_record(index, record or (records[0] if records else None))
            self._restore_selection(index)
        self._loading = False
        self._update_dirty()

    @staticmethod
    def _key(record):
        if record is None:
            return None
        return record.network_id if isinstance(record, AccessUser) else record.role_code

    def _affected(self, role_code):
        return sum(user.role_code == role_code for user in self.snapshot.users)

    def _show_record(self, index, record, new=False):
        loading = self._loading
        self._loading = True
        self._originals[index] = record
        self._new[index] = new
        self.editors[index].setEnabled(record is not None or new)
        if index == 0:
            value = record or AccessUser("", "", True, "")
            self.user_id.setText(value.network_id)
            self.user_id.setReadOnly(record is not None)
            self.user_name.setText(value.name)
            self.user_id.setCursorPosition(0)
            self.user_name.setCursorPosition(0)
            self.user_enabled.setChecked(value.enabled)
            self.user_role.setCurrentIndex(self.user_role.findData(value.role_code))
        else:
            value = record or AccessRole("", "", False, False, False)
            self.role_code.setText(value.role_code)
            self.role_code.setReadOnly(record is not None)
            self.role_description.setText(value.description)
            self.role_code.setCursorPosition(0)
            self.role_description.setCursorPosition(0)
            self.role_all_apps.setChecked(value.all_apps)
            self.role_update.setChecked(value.can_update_database)
            self.role_support.setChecked(value.can_write_support_files)
            self.role_group.set_value("affected", self._affected(value.role_code))
            while self.app_grid.count():
                item = self.app_grid.takeAt(0)
                item.widget().deleteLater()
            self.app_checks = {}
            unknown = sorted(value.apps.difference(APP_CODES).difference({"ADMIN"}))
            for position, code in enumerate((*APP_CODES, *unknown)):
                check = make_checkbox(code + (" (unrecognized)" if code in unknown else ""))
                check.setChecked(code in value.apps)
                check.setToolTip(code if code in APP_CODES else
                                 f"Existing unrecognized app code {code}; retained unless unchecked.")
                check.toggled.connect(self._update_dirty)
                self.app_grid.addWidget(check, position // 2, position % 2)
                self.app_checks[code] = check
            self._update_picker()
        self._baselines[index] = self._value(index)
        self._loading = loading
        if not loading:
            self._update_dirty()

    def _value(self, index):
        if index == 0:
            return AccessUser(
                self.user_id.text().strip().upper(), self.user_name.text().strip(),
                self.user_enabled.isChecked(), self.user_role.currentData() or "",
            )
        return AccessRole(
            self.role_code.text().strip().upper(), self.role_description.text().strip(),
            self.role_all_apps.isChecked(), self.role_update.isChecked(),
            self.role_support.isChecked(),
            frozenset(code for code, check in self.app_checks.items() if check.isChecked()),
        )

    @property
    def dirty(self):
        return any(self._is_dirty(index) for index in (0, 1))

    def _is_dirty(self, index):
        return self._new[index] or (
            self._baselines[index] is not None and self._value(index) != self._baselines[index]
        )

    def _update_dirty(self, *_args):
        if self._loading:
            return
        title = "Administrator" + (" *" if self.dirty else "")
        self.set_title(title)
        self.setWindowTitle(title)
        for index in (0, 1):
            self.save_buttons[index].setEnabled(not self._blocked and self._is_dirty(index))
            original = self._originals[index]
            can_delete = original is not None and not self._blocked
            if index == 1 and original:
                can_delete = can_delete and not self._affected(original.role_code)
                self.delete_buttons[index].setToolTip(
                    "Reassign every user before deleting this role."
                    if self._affected(original.role_code) else "Delete this unassigned role."
                )
            self.delete_buttons[index].setEnabled(can_delete)

    def _update_picker(self, *_args):
        all_apps = self.role_all_apps.isChecked()
        self.app_picker.setEnabled(not all_apps)
        self.app_scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget > QWidget { background: #E5E7EB; }"
            if all_apps else "QScrollArea { background: white; }"
        )
        self.app_note.setText(
            "AllApps is on — whitelist ignored; selections are preserved."
            if all_apps else "Allowed applications — select any of the 12 SuiteView apps."
        )
        self.app_note.setStyleSheet(
            "color: #6B7280; font-style: italic;" if all_apps else "color: #173659;"
        )

    def _discard_allowed(self):
        return not self.dirty or QMessageBox.question(
            self, "Unsaved changes", "Discard unsaved changes?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        ) == QMessageBox.StandardButton.Discard

    def _restore_selection(self, index):
        table = self.tables[index]
        selection = table.table_view.selectionModel()
        with QSignalBlocker(selection):
            selection.clear()
            key = self._key(self._originals[index])
            if key is not None:
                for row in range(table.model.rowCount()):
                    if table.model.index(row, 0).data() == key:
                        table.table_view.setCurrentIndex(table.model.index(row, 0))
                        table.table_view.selectRow(row)
                        break

    def _select_row(self, index, current):
        if self._loading or not current.isValid():
            return
        key = current.siblingAtColumn(0).data()
        if key == self._key(self._originals[index]) and not self._new[index]:
            return
        if not self._discard_allowed():
            self._restore_selection(index)
            # QTableView finishes updating the selected rows after currentRowChanged
            # during a mouse press. Restore again after that event has unwound.
            QTimer.singleShot(0, lambda: self._restore_selection(index))
            return
        records = self.snapshot.users if index == 0 else self.snapshot.roles
        record = next(record for record in records if self._key(record) == key)
        self._show_record(index, record)

    def _change_tab(self, index):
        if self._loading or index == self._tab:
            return
        if not self._discard_allowed():
            with QSignalBlocker(self.tabs):
                self.tabs.setCurrentIndex(self._tab)
            return
        old = self._tab
        self._show_record(old, self._originals[old])
        self._tab = index

    def new_record(self):
        if not self._blocked and self._discard_allowed():
            self._show_record(self._tab, None, new=True)
            self._restore_selection(self._tab)
            (self.user_id if self._tab == 0 else self.role_code).setFocus()

    def _set_status(self, action=""):
        access = "Developer access (source)" if has_developer_access() else "ADMIN"
        suffix = f" · {action}" if action else ""
        self.status.setText(f"Signed in: {self.snapshot.actor_id} · {access}{suffix}")

    def refresh(self):
        if not self._discard_allowed():
            return
        try:
            snapshot = self.repository.load()
        except Exception as error:
            self._report(error, "Refresh failed")
            return
        preferred = [self._key(record) for record in self._originals]
        self.snapshot = snapshot
        self._blocked = False
        self.tabs.setEnabled(True)
        self._populate(preferred)
        self._set_status("Refreshed")

    def _confirm(self, title, text):
        return QMessageBox.question(
            self, title, text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        ) == QMessageBox.StandardButton.Yes

    def save_record(self):
        if self._blocked or not self._is_dirty(self._tab):
            return
        index = self._tab
        value, original = self._value(index), self._originals[index]
        if index == 0:
            if original and original.enabled and not value.enabled:
                if not self._confirm(
                    "Disable user",
                    f"Mark {original.network_id} disabled?\n"
                    "Packaged SuiteView will deny their next app entry and protected write. "
                    "Source developer access is unaffected.",
                ):
                    return
        elif not self._confirm(
            "Save role",
            f"Save role {value.role_code}?\nThis affects {self._affected(value.role_code)} "
            "assigned user(s). Their stored app and write permissions use this shared role.\n"
            "Packaged SuiteView enforces these permissions on app entry and protected writes.",
        ):
            return
        try:
            if index == 0:
                self.repository.save_user(value, original=original)
            else:
                self.repository.save_role(value, original=original)
        except Exception as error:
            self._report(error, "Save failed — draft retained")
            return
        self._after_mutation("Saved", self._key(value))

    def delete_record(self):
        if self._blocked:
            return
        original = self._originals[self._tab]
        if original is None or not self._discard_allowed():
            return
        if self._tab == 1 and self._affected(original.role_code):
            QMessageBox.warning(self, "Role in use", "Reassign every user before deleting this role.")
            return
        if not self._confirm("Delete record", f"Permanently delete {self._key(original)}?"):
            return
        try:
            if self._tab == 0:
                self.repository.delete_user(original)
            else:
                self.repository.delete_role(original)
        except Exception as error:
            self._report(error, "Delete failed — draft retained")
            return
        self._after_mutation("Deleted", None)

    def _after_mutation(self, action, key):
        self.permissions_changed.emit()
        try:
            snapshot = self.repository.load()
        except Exception as error:
            # The commit succeeded. Never offer a repeat write using a stale original.
            self._blocked = True
            self.tabs.setEnabled(False)
            self._report(error, f"{action}, but reload failed — editing blocked; Refresh to recover")
            return
        preferred = [self._key(record) for record in self._originals]
        preferred[self._tab] = key
        self.snapshot = snapshot
        self._populate(preferred)
        self._set_status(action)

    def _report(self, error, title):
        logger.exception("Administrator: %s", title)
        if isinstance(error, PermissionError):
            self._blocked = True
            self.tabs.setEnabled(False)
        self.status.setText(f"{title}: {error}")
        self._update_dirty()
        QMessageBox.warning(self, title, str(error))

    def closeEvent(self, event):
        if self._discard_allowed():
            for index in (0, 1):
                self._show_record(index, self._originals[index])
                self._restore_selection(index)
            event.accept()
        else:
            event.ignore()
