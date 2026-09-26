"""Excel export helpers for the SuiteView File Explorer."""
from __future__ import annotations

import logging

from suiteview.file_nav.file_explorer_imports import *
from suiteview.file_nav.file_explorer_widgets import PrintDirectoryDialog

logger = logging.getLogger(__name__)


_DIRECTORY_HEADERS = ['Level', 'Type', 'Name', 'Full Path', 'Size', 'Modified', 'Extension']


class FileExplorerExportMixin:
    def export_details_to_excel(self):
        """Export the current details view to a new Excel file."""
        try:
            if openpyxl is None:
                raise ImportError("openpyxl is not available")
            proxy = self.details_view.model()
            if not proxy or proxy.rowCount() == 0:
                QMessageBox.information(self, "Export", "No data to export.")
                return
            wb = self._build_details_export_workbook(proxy)
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.xlsx', delete=False)
            temp_path = temp_file.name
            temp_file.close()
            wb.save(temp_path)
            os.startfile(temp_path)
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export to Excel:\n{str(e)}")

    def _build_details_export_workbook(self, proxy):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "File Explorer Export"
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF")
        column_count = proxy.columnCount()
        for col in range(column_count):
            header = proxy.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            cell = ws.cell(row=1, column=col + 1, value=str(header))
            cell.fill = header_fill
            cell.font = header_font
        for row in range(proxy.rowCount()):
            for col in range(column_count):
                index = proxy.index(row, col)
                data = proxy.data(index, Qt.ItemDataRole.DisplayRole)
                ws.cell(row=row + 2, column=col + 1, value=str(data) if data else "")
        self._autofit_openpyxl_columns(ws)
        return wb

    def _autofit_openpyxl_columns(self, worksheet):
        for col in worksheet.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    max_length = max(max_length, len(str(cell.value)))
                except (TypeError, ValueError):
                    logger.debug("Ignoring unmeasurable Excel cell", exc_info=True)
            worksheet.column_dimensions[column].width = min(max_length + 2, 50)

    def print_directory_to_excel(self):
        """Export current directory structure directly to Excel (no file saved)."""
        path = self._directory_print_start_path()
        dialog = PrintDirectoryDialog(path, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        progress = self._create_directory_print_progress()
        try:
            data, canceled = self._collect_directory_print_data(Path(path), dialog.get_options(), progress)
            progress.setLabelText("Canceled — opening Excel with partial results..." if canceled else "Opening Excel...")
            QApplication.processEvents()
            self._open_directory_print_excel(data, progress)
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Error", f"Failed to collect directory information:\n\n{str(e)}")

    def _directory_print_start_path(self):
        path = self.current_details_folder if getattr(self, 'current_details_folder', None) else self.get_selected_path()
        if path and Path(path).is_dir():
            return path
        onedrive_paths = self.get_onedrive_paths()
        return str(onedrive_paths[0]) if onedrive_paths else str(Path.home())

    def _create_directory_print_progress(self):
        progress = QProgressDialog("Collecting directory information...", "Cancel", 0, 0, self)
        progress.setWindowTitle("Print Directory")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        return progress

    def _collect_directory_print_data(self, root: Path, options, progress):
        data = [_DIRECTORY_HEADERS]
        counts = {"files": 0, "folders": 0, "last_ui_update": 0.0}
        if options['include_subdirs']:
            canceled = self._collect_recursive_directory_rows(root, data, counts, progress)
        else:
            canceled = self._collect_immediate_directory_rows(root, data, counts, progress)
        return data, canceled

    def _maybe_update_directory_progress(self, counts, progress):
        now = time.monotonic()
        if (now - counts["last_ui_update"]) < 0.15:
            return
        counts["last_ui_update"] = now
        progress.setLabelText(f"Scanning... {counts['folders']:,} folders, {counts['files']:,} files")
        QApplication.processEvents()

    def _collect_recursive_directory_rows(self, root: Path, data, counts, progress):
        progress.setLabelText("Scanning folders...")
        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath)
            level = len(current.relative_to(root).parts)
            if progress.wasCanceled():
                dirnames[:] = []
                filenames[:] = []
                return True
            if self._append_named_directory_rows(current, sorted(dirnames), level, data, counts, progress):
                dirnames[:] = []
                filenames[:] = []
                return True
            if self._append_named_file_rows(current, sorted(filenames), level, data, counts, progress):
                dirnames[:] = []
                filenames[:] = []
                return True
            self._maybe_update_directory_progress(counts, progress)
        return False

    def _collect_immediate_directory_rows(self, root: Path, data, counts, progress):
        try:
            items = sorted(root.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except OSError:
            items = []
        for item in items:
            if progress.wasCanceled():
                return True
            try:
                stat = item.stat()
                if item.is_dir():
                    data.append([0, 'Folder', item.name, str(item), '', self._format_directory_timestamp(stat), ''])
                    counts["folders"] += 1
                else:
                    data.append([0, 'File', item.name, str(item), self._format_file_size(stat.st_size), self._format_directory_timestamp(stat), item.suffix])
                    counts["files"] += 1
            except OSError:
                logger.debug("Skipping inaccessible directory print row", exc_info=True)
            self._maybe_update_directory_progress(counts, progress)
        return False

    def _append_named_directory_rows(self, current, dirnames, level, data, counts, progress):
        for dirname in dirnames:
            if progress.wasCanceled():
                return True
            folder_path = current / dirname
            try:
                stat = folder_path.stat()
                data.append([level, 'Folder', dirname, str(folder_path), '', self._format_directory_timestamp(stat), ''])
                counts["folders"] += 1
            except OSError:
                logger.debug("Skipping inaccessible folder during directory print", exc_info=True)
        return False

    def _append_named_file_rows(self, current, filenames, level, data, counts, progress):
        for filename in filenames:
            if progress.wasCanceled():
                return True
            file_path = current / filename
            try:
                stat = file_path.stat()
                data.append([level, 'File', filename, str(file_path), self._format_file_size(stat.st_size), self._format_directory_timestamp(stat), file_path.suffix])
                counts["files"] += 1
            except OSError:
                logger.debug("Skipping inaccessible file during directory print", exc_info=True)
        return False

    def _format_file_size(self, size):
        if size < 1024:
            return f"{size:,} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"

    def _format_directory_timestamp(self, stat_result):
        return datetime.fromtimestamp(stat_result.st_mtime).strftime("%Y-%m-%d %H:%M")

    def _open_directory_print_excel(self, data, progress):
        if os.name != 'nt':
            progress.close()
            QMessageBox.warning(self, "Not Supported", "Direct Excel opening is only supported on Windows.\n\nThis feature requires Microsoft Excel and COM automation.")
            return
        try:
            if win32com_dynamic is None:
                raise ImportError("pywin32 is not available")
            excel = win32com_dynamic.Dispatch('Excel.Application')
            excel.Visible = True
            wb = excel.Workbooks.Add()
            ws = wb.Worksheets(1)
            ws.Name = "Directory Contents"
            self._populate_directory_print_worksheet(ws, data, progress)
            progress.close()
            ws = None
            wb = None
            excel = None
        except ImportError:
            progress.close()
            QMessageBox.critical(self, "Excel COM Error", "Could not access Excel via COM automation.\n\nMake sure Microsoft Excel is installed and pywin32 is available.")
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Excel Error", f"Failed to open Excel:\n\n{str(e)}")

    def _populate_directory_print_worksheet(self, worksheet, data, progress):
        progress.setLabelText("Populating Excel...")
        if data:
            num_rows = len(data)
            num_cols = len(data[0])
            end_col_letter = chr(64 + num_cols)
            worksheet.Range(f"A1:{end_col_letter}{num_rows}").Value = data
            QApplication.processEvents()
        header_range = worksheet.Range(worksheet.Cells(1, 1), worksheet.Cells(1, len(_DIRECTORY_HEADERS)))
        header_range.Font.Bold = True
        header_range.Font.Color = 0xFFFFFF
        header_range.Interior.Color = 0x926636
        header_range.HorizontalAlignment = -4108
        progress.setLabelText("Formatting...")
        QApplication.processEvents()
        worksheet.Columns.AutoFit()
        worksheet.Range("A2").Select()
        worksheet.Application.ActiveWindow.FreezePanes = True
        worksheet.Range("A1").Select()
