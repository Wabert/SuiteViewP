"""Frameless mainframe dataset content-search window."""

import logging

import pandas as pd
from PyQt6.QtCore import Qt, QModelIndex
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from suiteview.mainframe_nav.content_search import ContentSearchThread
from suiteview.mainframe_nav.styles import (
    MAINFRAME_BORDER_COLOR,
    MAINFRAME_HEADER_COLORS,
    c,
    push_button_style,
    search_input_style,
    viewer_button_style,
)
from suiteview.ui.widgets.filter_table_view import FilterTableView
from suiteview.ui.widgets.frameless_window import FramelessWindowBase

logger = logging.getLogger(__name__)


class SearchContentWindow(FramelessWindowBase):
    """Standalone window for advanced dataset content searching."""

    def __init__(self, ftp_manager, parent=None):
        self.ftp_manager = ftp_manager
        self.datasets_to_search = []
        self.current_results = []
        self.search_thread = None
        super().__init__(
            title="🔍 Search Dataset Content",
            default_size=(1200, 800),
            min_size=(900, 620),
            parent=parent,
            header_colors=MAINFRAME_HEADER_COLORS,
            border_color=MAINFRAME_BORDER_COLOR,
        )

    def build_content(self) -> QWidget:
        body = QWidget()
        body.setStyleSheet("QWidget { background-color: #f8f9fa; }")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        layout.addWidget(self._build_search_criteria())
        layout.addWidget(self._build_splitter(), 1)
        self._refresh_dataset_table()
        self._refresh_results_table()
        return body

    def _build_search_criteria(self) -> QWidget:
        search_control_widget = QWidget()
        search_control_widget.setStyleSheet(
            "background-color: #f8f9fa; border: 1px solid #bdc3c7; border-radius: 3px;"
        )
        search_control_layout = QVBoxLayout(search_control_widget)
        search_control_layout.setContentsMargins(6, 3, 6, 3)
        search_control_layout.setSpacing(2)

        self.search_inputs = []
        self.case_sensitive_cbs = []
        self.allow_wildcard_cbs = []
        for index in range(4):
            search_control_layout.addLayout(self._build_search_row(index))

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        search_btn = QPushButton("Search")
        search_btn.setStyleSheet(push_button_style("search", font_size="8pt"))
        search_btn.clicked.connect(self.perform_search)
        button_layout.addWidget(search_btn)
        search_control_layout.addLayout(button_layout)
        search_control_widget.setSizePolicy(
            search_control_widget.sizePolicy().horizontalPolicy(),
            QSizePolicy.Policy.Fixed,
        )
        return search_control_widget

    def _build_search_row(self, index: int) -> QHBoxLayout:
        row_layout = QHBoxLayout()
        row_layout.setSpacing(6)

        search_label = QLabel(f"Search {index + 1}:")
        search_label.setStyleSheet(
            f"font-weight: bold; font-size: 8pt; color: {c('dark_text')}; min-width: 55px;"
        )
        row_layout.addWidget(search_label)

        search_input = QLineEdit()
        search_input.setPlaceholderText(f"Enter search string {index + 1}...")
        search_input.setStyleSheet(
            "QLineEdit { border: 1px solid #bdc3c7; border-radius: 2px; "
            "padding: 2px 4px; font-family: Consolas, monospace; "
            "font-size: 8pt; background-color: white; }"
        )
        row_layout.addWidget(search_input, 1)
        self.search_inputs.append(search_input)

        case_cb = QCheckBox("Case Sensitive")
        case_cb.setStyleSheet("font-size: 8pt;")
        row_layout.addWidget(case_cb)
        self.case_sensitive_cbs.append(case_cb)

        wildcard_cb = QCheckBox("Allow Wildcard")
        wildcard_cb.setStyleSheet("font-size: 8pt;")
        row_layout.addWidget(wildcard_cb)
        self.allow_wildcard_cbs.append(wildcard_cb)
        return row_layout

    def _build_splitter(self) -> QSplitter:
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(self._build_dataset_panel())
        main_splitter.addWidget(self._build_results_panel())
        main_splitter.setSizes([500, 700])
        return main_splitter

    def _build_dataset_panel(self) -> QWidget:
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5)
        left_layout.addWidget(self._section_label("📋 Datasets to Search", "#e8f4f8"))

        dataset_info = QLabel("Right-click datasets in Mainframe Nav and select 'Add to Search'")
        dataset_info.setStyleSheet("color: #7f8c8d; font-size: 8pt; font-style: italic; padding: 2px;")
        left_layout.addWidget(dataset_info)

        dataset_controls = QHBoxLayout()
        dataset_filter_label = QLabel("Filter:")
        dataset_filter_label.setStyleSheet("font-size: 9pt; color: #34495e;")
        dataset_controls.addWidget(dataset_filter_label)

        self.dataset_filter = QLineEdit()
        self.dataset_filter.setPlaceholderText("Filter dataset list...")
        self.dataset_filter.setStyleSheet(search_input_style())
        self.dataset_filter.textChanged.connect(self.filter_dataset_list)
        dataset_controls.addWidget(self.dataset_filter)

        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.setStyleSheet(push_button_style("danger", font_size="9pt"))
        clear_all_btn.clicked.connect(self.clear_all_datasets)
        dataset_controls.addWidget(clear_all_btn)
        left_layout.addLayout(dataset_controls)

        self.dataset_table = self._create_filter_table()
        self.dataset_table.table_view.doubleClicked.connect(self.view_dataset)
        self.dataset_table.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.dataset_table.table_view.customContextMenuRequested.connect(self.show_dataset_context_menu)
        left_layout.addWidget(self.dataset_table)
        return left_widget

    def _build_results_panel(self) -> QWidget:
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)

        results_header_layout = QHBoxLayout()
        results_header_layout.addWidget(self._section_label("✓ Datasets with Matches", "#e8f8f5"))
        self.results_info_label = QLabel("")
        self.results_info_label.setStyleSheet("color: #7f8c8d; font-style: italic; font-size: 8pt; padding: 4px;")
        results_header_layout.addWidget(self.results_info_label)
        results_header_layout.addStretch()
        right_layout.addLayout(results_header_layout)

        self.results_table = self._create_filter_table(selection_bg="#27ae60", selection_fg="white")
        self.results_table.table_view.doubleClicked.connect(self.view_result_details)
        right_layout.addWidget(self.results_table)

        copy_btn_layout = QHBoxLayout()
        copy_btn_layout.addStretch()
        copy_results_btn = QPushButton("📋 Copy Results")
        copy_results_btn.setStyleSheet(push_button_style("neutral", font_size="9pt"))
        copy_results_btn.clicked.connect(self.copy_results)
        copy_btn_layout.addWidget(copy_results_btn)
        right_layout.addLayout(copy_btn_layout)
        return right_widget

    def _section_label(self, text: str, background: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            f"font-weight: bold; font-size: 10pt; color: {c('dark_text')}; "
            f"padding: 4px 6px; background-color: {background}; border-radius: 3px;"
        )
        return label

    def _create_filter_table(self, *, selection_bg: str = "#3498db", selection_fg: str = "white") -> FilterTableView:
        table = FilterTableView(self)
        table.search_bar.hide()
        table.apply_ledger_style(
            header_bg="#e8f4f8",
            header_fg=c("dark_text"),
            border="#bdc3c7",
            selection_bg=selection_bg,
            selection_fg=selection_fg,
        )
        table.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.table_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.header.setStretchLastSection(True)
        return table

    def add_dataset(self, dataset_name, full_path, dsorg=""):
        """Add a dataset to the search list."""
        if any(item["full_path"] == full_path for item in self.datasets_to_search):
            return

        if dsorg == "PO":
            QMessageBox.warning(
                self,
                "Cannot Add PO Dataset",
                f"{dataset_name} is a PO (partitioned) dataset and cannot be searched directly.\n\n"
                "Please add its members instead.",
            )
            return

        self.datasets_to_search.append(
            {
                "name": dataset_name,
                "full_path": full_path,
                "dsorg": dsorg,
            }
        )
        self._refresh_dataset_table(self.dataset_filter.text() if hasattr(self, "dataset_filter") else "")
        logger.info(f"Added {dataset_name} to search list")

    def filter_dataset_list(self, text):
        """Filter the dataset list."""
        self._refresh_dataset_table(text)

    def clear_all_datasets(self):
        """Clear all datasets from the list."""
        self.datasets_to_search.clear()
        self.current_results = []
        self.results_info_label.setText("")
        self._refresh_dataset_table()
        self._refresh_results_table()

    def show_dataset_context_menu(self, position):
        """Show context menu for dataset table."""
        row_data = self._row_data_at(self.dataset_table, position)
        if row_data is None:
            return

        menu = QMenu(self)
        remove_action = menu.addAction("Remove from List")
        view_action = menu.addAction("View Dataset")
        action = menu.exec(self.dataset_table.table_view.viewport().mapToGlobal(position))

        if action == remove_action:
            self.datasets_to_search = [
                item for item in self.datasets_to_search if item["full_path"] != row_data["Path"]
            ]
            self._refresh_dataset_table(self.dataset_filter.text())
        elif action == view_action:
            self.view_dataset_for_row(row_data)

    def view_dataset(self, index: QModelIndex):
        """View dataset content in a dialog."""
        row_data = self._row_data_from_index(self.dataset_table, index)
        if row_data is not None:
            self.view_dataset_for_row(row_data)

    def view_dataset_for_row(self, row_data: dict):
        dataset_name = row_data["Dataset"]
        full_path = row_data["Path"]
        try:
            content, total_lines = self.ftp_manager.read_dataset(full_path, max_lines=1000)
            if total_lines == 0:
                QMessageBox.warning(self, "No Content", f"Dataset {dataset_name} is empty or could not be read.")
                return
            self._show_text_dialog(
                f"View: {dataset_name}",
                f"Showing first 1000 lines of {dataset_name} (Total: {total_lines} lines)",
                content,
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to view dataset:\n{str(e)}")
            logger.error(f"Error viewing dataset {dataset_name}: {e}")

    def perform_search(self):
        """Perform the search."""
        if not self.datasets_to_search:
            QMessageBox.warning(self, "No Datasets", "Please add datasets to search first.")
            return

        search_strings = [
            search_input.text().strip()
            for search_input in self.search_inputs
            if search_input.text().strip()
        ]
        if not search_strings:
            QMessageBox.warning(self, "No Search Strings", "Please enter at least one search string.")
            return

        case_sensitive = self.case_sensitive_cbs[0].isChecked() if self.case_sensitive_cbs else False
        progress_dialog, progress_label = self._build_progress_dialog()
        self.search_thread = ContentSearchThread(
            self.ftp_manager,
            self.datasets_to_search,
            search_strings,
            case_sensitive,
            False,
            "",
        )
        cancel_btn = progress_dialog.findChild(QPushButton, "cancelSearchButton")
        cancel_btn.clicked.connect(self.search_thread.cancel)
        cancel_btn.clicked.connect(progress_dialog.close)
        self.search_thread.progress_update.connect(
            lambda msg, curr, total: progress_label.setText(f"{msg} ({curr} of {total})")
        )
        self.search_thread.search_complete.connect(self.display_results)
        self.search_thread.search_complete.connect(progress_dialog.close)
        self.search_thread.start()
        progress_dialog.exec()

    def _build_progress_dialog(self) -> tuple[QDialog, QLabel]:
        progress_dialog = QDialog(self)
        progress_dialog.setWindowTitle("Searching...")
        progress_dialog.setModal(True)
        progress_dialog.resize(400, 100)
        progress_layout = QVBoxLayout(progress_dialog)
        progress_label = QLabel(f"Searching dataset 0 of {len(self.datasets_to_search)}...")
        progress_layout.addWidget(progress_label)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelSearchButton")
        cancel_btn.setStyleSheet(push_button_style("danger"))
        progress_layout.addWidget(cancel_btn)
        return progress_dialog, progress_label

    def display_results(self, result_data):
        """Display search results in the results table."""
        results = result_data.get("results", [])
        errors = result_data.get("errors", [])
        skipped = result_data.get("skipped", [])
        self.current_results = results
        self._update_results_info(results, skipped, errors)
        self._refresh_results_table()
        logger.info(f"Display complete: {len(results)} results, {len(skipped)} skipped, {len(errors)} errors")

    def _update_results_info(self, results: list, skipped: list, errors: list):
        info_parts = []
        if results:
            info_parts.append(f"{len(results)} with matches")
        if skipped:
            info_parts.append(f"{len(skipped)} skipped")
        if errors:
            info_parts.append(f"{len(errors)} errors")

        if results:
            self.results_info_label.setText(", ".join(info_parts))
            self.results_info_label.setStyleSheet("color: #27ae60; font-style: italic; font-size: 9pt; padding: 6px;")
        else:
            suffix = f" ({', '.join(info_parts[1:])})" if info_parts[1:] else ""
            self.results_info_label.setText("No matches found" + suffix)
            self.results_info_label.setStyleSheet("color: #e74c3c; font-style: italic; font-size: 9pt; padding: 6px;")

    def view_result_details(self, index: QModelIndex):
        """View detailed match information for a result."""
        row_data = self._row_data_from_index(self.results_table, index)
        if row_data is None:
            return
        result_index = int(row_data["_result_index"])
        if not 0 <= result_index < len(self.current_results):
            return
        result = self.current_results[result_index]
        self._show_text_dialog(
            f"Match Details: {result['dataset']}",
            f"Dataset: {result['dataset']}\nPath: {result['full_path']}",
            self._format_result_details(result),
        )

    def copy_results(self):
        """Copy results to clipboard."""
        if not self.current_results:
            return
        clipboard = QGuiApplication.clipboard()
        clipboard.setText("\n".join(self._format_result_summary(result) for result in self.current_results))

    def _refresh_dataset_table(self, filter_text: str = ""):
        rows = [
            {"Dataset": item["name"], "Path": item["full_path"]}
            for item in self.datasets_to_search
            if not filter_text or filter_text.lower() in item["name"].lower()
        ]
        self.dataset_table.set_dataframe(pd.DataFrame(rows, columns=["Dataset", "Path"]), limit_rows=False)
        self.dataset_table.table_view.resizeColumnsToContents()
        self.dataset_table.header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def _refresh_results_table(self):
        rows = []
        for index, result in enumerate(self.current_results):
            total_matches = sum(len(match_group["matches"]) for match_group in result["matches"])
            rows.append(
                {
                    "Dataset": result["dataset"],
                    "Matches": str(total_matches),
                    "Path": result["full_path"],
                    "_result_index": index,
                }
            )
        self.results_table.set_dataframe(
            pd.DataFrame(rows, columns=["Dataset", "Matches", "Path", "_result_index"]),
            limit_rows=False,
        )
        self.results_table.table_view.hideColumn(3)
        self.results_table.table_view.resizeColumnsToContents()
        self.results_table.header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

    def _row_data_at(self, table: FilterTableView, position) -> dict | None:
        return self._row_data_from_index(table, table.table_view.indexAt(position))

    def _row_data_from_index(self, table: FilterTableView, index: QModelIndex) -> dict | None:
        if not index.isValid() or table.model is None or table.df is None:
            return None
        source_index = table.model._display_indices[index.row()]
        return table.df.loc[source_index].to_dict()

    def _show_text_dialog(self, title: str, header_text: str, content: str):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(900, 700)
        layout = QVBoxLayout(dialog)
        header = QLabel(header_text)
        header.setStyleSheet("font-weight: bold; padding: 8px; background-color: #e8f4f8; border-radius: 3px;")
        layout.addWidget(header)
        details_text = QTextEdit()
        details_text.setReadOnly(True)
        details_text.setFont(QFont("Courier New", 9))
        details_text.setPlainText(content)
        layout.addWidget(details_text)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(viewer_button_style())
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        dialog.exec()

    def _format_result_details(self, result: dict) -> str:
        output = []
        for match_group in result["matches"]:
            search_str = match_group["search_string"]
            matches = match_group["matches"]
            output.append(f"\n{'=' * 80}")
            output.append(f"Search String: '{search_str}' - {len(matches)} match(es) found")
            output.append(f"{'-' * 80}")
            for match in matches:
                output.append(f"  Line {match['line_number']}: {match['line_content']}")
        return "\n".join(output)

    def _format_result_summary(self, result: dict) -> str:
        output = [
            f"\n{'=' * 80}",
            f"Dataset: {result['dataset']}",
            f"Path: {result['full_path']}",
            f"{'-' * 80}",
        ]
        for match_group in result["matches"]:
            search_str = match_group["search_string"]
            matches = match_group["matches"]
            output.append(f"\n  Search String: '{search_str}' - {len(matches)} match(es)")
            for match in matches:
                output.append(f"    Line {match['line_number']}: {match['line_content']}")
        return "\n".join(output)
