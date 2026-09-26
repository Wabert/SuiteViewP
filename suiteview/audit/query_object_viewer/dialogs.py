"""Dialogs used by QueryObject Viewer."""
from __future__ import annotations

from .common import *  # noqa: F401,F403 - private split module shares viewer globals.

class _TablePreviewDialog(QDialog):
    """Popup preview of a table's data with adjustable row count and search.

    The embedded :class:`FilterTableView` provides the search bar; the Rows
    input lets the user change how many rows to pull and reload in place.
    """

    reload_requested = pyqtSignal(int)  # requested row count

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preview")
        self.setStyleSheet("QDialog { background: #F0F0F0; }")
        self.resize(760, 480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        controls = QHBoxLayout()
        controls.setSpacing(6)
        controls.addWidget(QLabel("Rows"))
        self.edit_rows = QLineEdit("100")
        self.edit_rows.setFixedWidth(60)
        self.edit_rows.setStyleSheet(
            "QLineEdit { background: white; border: 1px solid #A0C4E8; padding: 2px 4px; }")
        self.edit_rows.returnPressed.connect(self._emit_reload)
        controls.addWidget(self.edit_rows)
        self.btn_reload = QPushButton("Reload")
        self.btn_reload.setFont(_FONT_BOLD)
        self.btn_reload.setFixedHeight(24)
        self.btn_reload.setStyleSheet(_BTN_STYLE)
        self.btn_reload.clicked.connect(self._emit_reload)
        controls.addWidget(self.btn_reload)
        controls.addStretch(1)
        lay.addLayout(controls)
        self.table = FilterTableView(self)
        pv = self.table.table_view
        pv.setShowGrid(False)
        pv.verticalHeader().setVisible(False)
        pv.verticalHeader().setDefaultSectionSize(16)
        lay.addWidget(self.table, 1)

    def rows_value(self) -> int:
        try:
            rows = int(self.edit_rows.text().strip() or "100")
        except ValueError:
            rows = 100
            self.edit_rows.setText("100")
        return max(1, rows)

    def _emit_reload(self) -> None:
        self.reload_requested.emit(self.rows_value())

    def set_dataframe(self, dataframe) -> None:
        self.table.set_dataframe(dataframe, limit_rows=False)

    def set_title(self, name: str) -> None:
        self.setWindowTitle(f"Preview: {name}")



class _RegisterOdbcDialog(QDialog):
    """Register (or edit) an ODBC DSN as a named, persisted data source.

    You pick from the installed Windows DSNs or type a name, give it a friendly
    label + notes, and can Test the connection before saving. Produces a
    ``RegisteredDataSource`` on ``result_source`` when accepted.
    """

    def __init__(self, parent=None, *, dsn: str = "", existing=None):
        super().__init__(parent)

        self._existing = existing
        self.result_source = None
        self.setWindowTitle("Register ODBC Data Source")
        self.setMinimumWidth(440)
        self.setStyleSheet(
            "QDialog { background: #F0F0F0; }"
            "QLabel { color: #0D3A7A; }"
            "QLineEdit, QComboBox { background: white; border: 1px solid #A0C4E8;"
            " padding: 3px 4px; }")

        grid = QGridLayout(self)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("ODBC DSN"), 0, 0)
        self.cmb_dsn = QComboBox()
        self.cmb_dsn.setEditable(True)
        for name, driver in list_installed_dsns():
            self.cmb_dsn.addItem(name)
            self.cmb_dsn.setItemData(self.cmb_dsn.count() - 1, driver, Qt.ItemDataRole.ToolTipRole)
        self.cmb_dsn.setCurrentText(dsn or (existing.dsn if existing else ""))
        grid.addWidget(self.cmb_dsn, 0, 1, 1, 2)

        grid.addWidget(QLabel("Name"), 1, 0)
        self.edit_name = QLineEdit(existing.name if existing else (dsn or ""))
        grid.addWidget(self.edit_name, 1, 1, 1, 2)

        grid.addWidget(QLabel("Notes"), 2, 0)
        self.edit_notes = QLineEdit(existing.notes if existing else "")
        grid.addWidget(self.edit_notes, 2, 1, 1, 2)

        self.lbl_test = QLabel("")
        self.lbl_test.setFont(_FONT_SMALL)
        grid.addWidget(self.lbl_test, 3, 1, 1, 2)

        btn_test = QPushButton("Test Connection")
        btn_test.setStyleSheet(_BTN_STYLE)
        btn_test.clicked.connect(self._on_test)
        grid.addWidget(btn_test, 4, 0)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            "Save" if existing is None else "Update")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        grid.addWidget(buttons, 4, 1, 1, 2)

    def _current_dsn(self) -> str:
        return self.cmb_dsn.currentText().strip()

    def _on_test(self) -> None:

        dsn = self._current_dsn()
        if not dsn:
            self.lbl_test.setText("Enter a DSN first.")
            self.lbl_test.setStyleSheet("color: #9A7A00;")
            return
        ok, message = probe_dsn_connection(dsn)
        self.lbl_test.setText("✓ Connected" if ok else f"✗ {message[:90]}")
        self.lbl_test.setStyleSheet("color: #1E7E34;" if ok else "color: #B71C1C;")

    def _on_accept(self) -> None:

        dsn = self._current_dsn()
        if not dsn:
            QMessageBox.warning(self, "DSN Required", "Pick or type an ODBC DSN.")
            return
        name = self.edit_name.text().strip() or dsn
        notes = self.edit_notes.text().strip()
        if self._existing is not None:
            ds = self._existing
            ds.name, ds.dsn, ds.notes = name, dsn, notes
            ds.dialect = detect_dialect(dsn)
            ds.updated_at = datetime.now()
        else:
            ds = RegisteredDataSource(
                name=name, kind=KIND_ODBC, dsn=dsn,
                dialect=detect_dialect(dsn), notes=notes)
        self.result_source = ds
        self.accept()


class _RegisterAccessDialog(QDialog):
    """Register (or edit) an MS Access file as a named, persisted data source.

    Access connects DSN-less (driver + file path), so you pick a ``.accdb`` /
    ``.mdb`` file, name it, and can Test the connection. Produces a
    ``RegisteredDataSource`` (kind=access) on ``result_source`` when accepted.
    """

    def __init__(self, parent=None, *, path: str = "", existing=None):
        super().__init__(parent)
        self._existing = existing
        self.result_source = None
        self.setWindowTitle("Register MS Access Data Source")
        self.setMinimumWidth(500)
        self.setStyleSheet(
            "QDialog { background: #F0F0F0; }"
            "QLabel { color: #0D3A7A; }"
            "QLineEdit { background: white; border: 1px solid #A0C4E8; padding: 3px 4px; }")

        grid = QGridLayout(self)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("Access file"), 0, 0)
        self.edit_path = QLineEdit(path or (existing.path if existing else ""))
        grid.addWidget(self.edit_path, 0, 1)
        btn_browse = QPushButton("Browse…")
        btn_browse.setStyleSheet(_BTN_STYLE)
        btn_browse.clicked.connect(self._on_browse)
        grid.addWidget(btn_browse, 0, 2)

        grid.addWidget(QLabel("Name"), 1, 0)
        default_name = existing.name if existing else (Path(path).stem if path else "")
        self.edit_name = QLineEdit(default_name)
        grid.addWidget(self.edit_name, 1, 1, 1, 2)

        grid.addWidget(QLabel("Notes"), 2, 0)
        self.edit_notes = QLineEdit(existing.notes if existing else "")
        grid.addWidget(self.edit_notes, 2, 1, 1, 2)

        self.lbl_test = QLabel("")
        self.lbl_test.setFont(_FONT_SMALL)
        grid.addWidget(self.lbl_test, 3, 1, 1, 2)

        btn_test = QPushButton("Test Connection")
        btn_test.setStyleSheet(_BTN_STYLE)
        btn_test.clicked.connect(self._on_test)
        grid.addWidget(btn_test, 4, 0)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            "Save" if existing is None else "Update")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        grid.addWidget(buttons, 4, 1, 1, 2)

    def _on_browse(self) -> None:
        start = self.edit_path.text().strip() or str(Path.home())
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select MS Access database", start,
            "Access Databases (*.accdb *.mdb);;All Files (*.*)")
        if file_path:
            self.edit_path.setText(file_path)
            if not self.edit_name.text().strip():
                self.edit_name.setText(Path(file_path).stem)

    def _on_test(self) -> None:

        ok, message = probe_access_connection(self.edit_path.text().strip())
        self.lbl_test.setText("✓ Connected" if ok else f"✗ {message[:90]}")
        self.lbl_test.setStyleSheet("color: #1E7E34;" if ok else "color: #B71C1C;")

    def _on_accept(self) -> None:

        path = self.edit_path.text().strip()
        if not path:
            QMessageBox.warning(self, "File Required", "Pick an MS Access file.")
            return
        name = self.edit_name.text().strip() or Path(path).stem
        notes = self.edit_notes.text().strip()
        if self._existing is not None:
            ds = self._existing
            ds.name, ds.path, ds.notes, ds.dialect = name, path, notes, ACCESS
            ds.updated_at = datetime.now()
        else:
            ds = RegisteredDataSource(
                name=name, kind=KIND_ACCESS, path=path, dialect=ACCESS, notes=notes)
        self.result_source = ds
        self.accept()



class FileObjectPreviewDialog(QDialog):
    """Small query surface for QueryObjects."""

    def __init__(self, query_object: QueryObject, parent=None):
        super().__init__(parent)
        self._query_object = query_object
        self.setWindowTitle(f"Preview Data - {query_object.name}")
        self.resize(880, 520)
        self._build_ui()
        self._run_preview()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)

        self.edit_columns = QLineEdit(
            ", ".join(field.name for field in self._query_object.fields)
        )
        self.edit_columns.setFont(_FONT)
        self.edit_columns.setPlaceholderText("Columns")
        top.addWidget(QLabel("Columns"))
        top.addWidget(self.edit_columns, 2)

        self.edit_filter = QLineEdit()
        self.edit_filter.setFont(_FONT)
        self.edit_filter.setPlaceholderText("Filter")
        top.addWidget(QLabel("Filter"))
        top.addWidget(self.edit_filter, 2)

        self.edit_limit = QLineEdit("500")
        self.edit_limit.setFont(_FONT)
        self.edit_limit.setFixedWidth(60)
        top.addWidget(QLabel("Rows"))
        top.addWidget(self.edit_limit)

        self.btn_run = QPushButton("Run")
        self.btn_run.setFont(_FONT_BOLD)
        self.btn_run.setFixedSize(70, 26)
        self.btn_run.setStyleSheet(_BTN_STYLE)
        self.btn_run.clicked.connect(self._run_preview)
        top.addWidget(self.btn_run)
        root.addLayout(top)

        self.table = FilterTableView(self)
        root.addWidget(self.table, 1)

        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_FONT_SMALL)
        self.lbl_status.setStyleSheet("color: #555;")
        root.addWidget(self.lbl_status)

    def _run_preview(self):
        columns = [
            column.strip()
            for column in self.edit_columns.text().split(",")
            if column.strip()
        ]
        try:
            limit = int(self.edit_limit.text().strip() or "500")
        except ValueError:
            QMessageBox.warning(self, "Invalid Rows", "Rows must be a number.")
            return
        try:
            if self._query_object.kind == OBJECT_KIND_ADHOC_SOURCE:
                df = query_adhoc_object(
                    self._query_object,
                    columns=columns,
                    filter_expr=self.edit_filter.text(),
                    limit=limit,
                )
            else:
                df = self._query_sql_object(columns=columns, filter_expr=self.edit_filter.text(), limit=limit)
        except Exception as exc:
            QMessageBox.warning(self, "Preview Failed", str(exc))
            return
        self.table.set_dataframe(df, limit_rows=False)
        self.lbl_status.setText(f"{len(df)} rows x {len(df.columns)} columns")

    def _query_sql_object(self, *, columns: list[str], filter_expr: str, limit: int) -> pd.DataFrame:
        sql = self._query_object.sql.strip().rstrip(";")
        dsn = self._query_object.dsn.strip()
        if not sql or not dsn:
            raise ValueError("This object does not have saved SQL and DSN information to preview.")
        preview_sql = _limited_preview_sql(sql, limit, _preview_dialect_for_object(self._query_object))
        result_columns, rows = execute_odbc_query(dsn, preview_sql)
        df = pd.DataFrame([list(row) for row in rows], columns=result_columns)
        if columns:
            available = [column for column in columns if column in df.columns]
            if available:
                df = df[available]
        if filter_expr.strip():
            df = df.query(filter_expr.strip(), engine="python")
        return df
