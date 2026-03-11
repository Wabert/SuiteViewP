"""
Policy Support tab - Manages a folder-based workflow for ad-hoc policy questions.

Three-column layout:
  1. Task Categories  — drag a category onto Policy Subfolders to create that task folder
  2. Policy Subfolders — mini file explorer; accepts drops from Task Categories (creates folder)
                         and from Available Tools (copies file)
  3. Available Tools   — home shows 8 pinned tool folders; double-click to navigate in;
                         drag a file onto Policy Subfolders to copy it there

Folder structure:
    <Process_Control>/Policy Support/POLICY_LIBRARY/<ProductType>/<Co>_<PolicyNo>/<TaskCategory>/
"""

import json
import os
import shutil
from typing import Optional, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox, QGridLayout,
    QMessageBox, QAbstractItemView, QInputDialog, QMenu,
    QStyledItemDelegate, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QSize, QMimeData, QUrl
from PyQt6.QtGui import QColor, QDrag, QPixmap, QPainter, QFont

from ..styles import (
    WHITE, GRAY_DARK, GRAY_MID, GRAY_LIGHT,
    GREEN_DARK, GREEN_PRIMARY, GREEN_LIGHT, GREEN_SUBTLE,
    GOLD_PRIMARY, GOLD_TEXT, GOLD_DARK, GOLD_LIGHT,
    POLICY_INFO_FRAME_STYLE,
)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _get_process_control_dir() -> str:
    username = os.environ.get("USERNAME", os.environ.get("USER", "unknown"))
    return os.path.join(
        "C:\\Users", username,
        "OneDrive - American National Insurance Company",
        "Life Product - Process_Control",
    )

def _get_policy_support_dir() -> str:
    return os.path.join(_get_process_control_dir(), "Policy Support")

def _get_abr_dir() -> str:
    return os.path.join(
        _get_process_control_dir(),
        "Task",
        "Accelerated Death Benefit (ABR11 & ABR14)",
    )


# ---------------------------------------------------------------------------
# Pinned tool folders shown on the Available Tools home screen
# Each entry: (display_label, relative_path_from_process_control)
# ---------------------------------------------------------------------------

TOOL_FOLDERS = [
    ("Tools\\Illustration\\RERUN",
     r"Tools\Illustration\RERUN"),
    ("Tools\\Illustration\\Product Models\\TERM",
     r"Tools\Illustration\Product Models\TERM"),
    ("Task\\Policy Support\\Term Premiums Illustrations\\TERM TEMPLATE",
     r"Task\Policy Support\Term Premiums Illustrations\TERM TEMPLATE"),
    ("Task\\Policy Support\\Guideline and TAMRA\\Guideline Adjust for Exception Prems",
     r"Task\Policy Support\Guideline and TAMRA\Guideline Adjust for Exception Prems"),
    ("Cyberlife Reference Files\\CVF",
     r"Cyberlife Reference Files\CVF"),
    ("Task\\Policy Support\\Interpolated_Terminal_Reserve",
     r"Task\Policy Support\Interpolated_Terminal_Reserve"),
    ("Task\\Policy Support",
     r"Task\Policy Support"),
    ("Tools\\Whole Life Nonforfeiture Calc",
     r"Tools\Whole Life Nonforfeiture Calc"),
    ("Task\\Accelerated Death Benefit (ABR11 & ABR14)",
     r"Task\Accelerated Death Benefit (ABR11 & ABR14)"),
]

# Absolute-path tool folders (not relative to Process Control)
_ABS_TOOL_FOLDERS = [
    ("Cyberlife Reference Files",
     r"C:\Users\ab7y02\OneDrive - American National Insurance Company\Life Product - Data\Cyberlife Reference Files"),
]


# ---------------------------------------------------------------------------
# Default task categories
# ---------------------------------------------------------------------------

DEFAULT_TASK_CATEGORIES = [
    "Annuity_Rider",
    "Cash_Value_Quote",
    "Decrease",
    "GLP_Exception",
    "Illustration",
    "Increase",
    "Interpolated_Terminal_Reserve",
    "Mistatement",
    "Nonforfeiture",
    "Product_Contract_and_Specs",
    "Reinstatement",
    "Time_Driven_Error",
]


# ---------------------------------------------------------------------------
# User task storage
# ---------------------------------------------------------------------------

def _get_user_tasks_path() -> str:
    app_data = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")), "SuiteView"
    )
    os.makedirs(app_data, exist_ok=True)
    return os.path.join(app_data, "policy_support_tasks.json")

def _load_user_tasks() -> List[str]:
    path = _get_user_tasks_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return sorted(data) if isinstance(data, list) else []
    except Exception:
        return []

def _save_user_tasks(tasks: List[str]):
    path = _get_user_tasks_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(set(tasks)), f, indent=2)


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

_CONTEXT_MENU_STYLE = f"""
    QMenu {{
        background-color: #F0F0F0;
        border: 1px solid {GRAY_DARK};
        padding: 2px;
        font-size: 11px;
    }}
    QMenu::item {{ padding: 3px 20px 3px 8px; color: #1a1a1a; }}
    QMenu::item:selected {{ background-color: {GOLD_LIGHT}; color: {GREEN_DARK}; }}
    QMenu::item:disabled {{ color: #999999; }}
    QMenu::separator {{ height: 1px; background: {GRAY_MID}; margin: 2px 4px; }}
"""

_LIST_STYLE = f"""
    QListWidget {{
        font-size: 11px;
        border: none;
        background-color: {WHITE};
        outline: none;
        padding: 0px;
        margin: 0px;
    }}
    QListWidget::item {{
        padding: 0px 4px;
        margin: 0px;
        border: none;
        min-height: 0px;
    }}
    QListWidget::item:hover   {{ background-color: {GREEN_SUBTLE}; }}
    QListWidget::item:selected {{ background-color: {GOLD_LIGHT}; color: {GREEN_DARK}; font-weight: bold; }}
"""

_ACTION_BTN_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {GOLD_TEXT}, stop:1 {GOLD_PRIMARY});
        color: {GREEN_DARK};
        border: 1px solid {GOLD_DARK};
        border-radius: 3px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: bold;
        min-height: 18px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {GOLD_PRIMARY}, stop:1 {GOLD_DARK});
        color: {WHITE};
    }}
    QPushButton:pressed {{ background-color: {GOLD_DARK}; }}
    QPushButton:disabled {{
        background: {GRAY_MID}; color: {GRAY_DARK}; border-color: {GRAY_MID};
    }}
"""

_MODE_BTN_ACTIVE_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {GREEN_PRIMARY}, stop:1 {GREEN_DARK});
        color: {WHITE};
        border: 2px solid {GREEN_DARK};
        border-radius: 4px;
        padding: 4px 16px;
        font-size: 12px;
        font-weight: bold;
        min-height: 22px;
    }}
"""

_MODE_BTN_INACTIVE_STYLE = f"""
    QPushButton {{
        background: {GRAY_LIGHT};
        color: {GRAY_DARK};
        border: 1px solid {GRAY_MID};
        border-radius: 4px;
        padding: 4px 16px;
        font-size: 12px;
        font-weight: bold;
        min-height: 22px;
    }}
    QPushButton:hover {{
        background: {GREEN_SUBTLE};
        color: {GREEN_DARK};
        border-color: {GREEN_PRIMARY};
    }}
"""

_NAV_BTN_STYLE = f"""
    QPushButton {{
        background: {GREEN_SUBTLE};
        color: {GREEN_DARK};
        border: 1px solid {GREEN_PRIMARY};
        border-radius: 3px;
        padding: 1px 5px;
        font-size: 11px;
        font-weight: bold;
        min-height: 16px;
        max-height: 18px;
    }}
    QPushButton:hover {{ background: {GREEN_PRIMARY}; color: {WHITE}; }}
    QPushButton:disabled {{ background: {GRAY_LIGHT}; color: {GRAY_MID}; border-color: {GRAY_MID}; }}
"""

_PATH_BAR_STYLE = f"""
    font-size: 10px;
    color: {GREEN_DARK};
    background: {GREEN_SUBTLE};
    border: 1px solid {GREEN_PRIMARY};
    border-radius: 3px;
    padding: 1px 4px;
"""

_STATUS_STYLE = f"""
    font-size: 10px; color: {GRAY_DARK};
    background: transparent; border: none; padding: 2px 4px;
"""

_PATH_LABEL_STYLE = f"""
    font-size: 10px; color: {GREEN_DARK};
    background: {GREEN_SUBTLE};
    border: 1px solid {GREEN_PRIMARY};
    border-radius: 3px; padding: 3px 6px;
"""

# ── ABR (Crimson) theme overrides ──────────────────────────────────────────
# These mirror the green/gold styles above but use ABR crimson/slate colours.

_CRIMSON_DARK    = "#5C0A14"
_CRIMSON_PRIMARY = "#8B1A2A"
_CRIMSON_RICH    = "#A52535"
_CRIMSON_LIGHT   = "#C96070"
_CRIMSON_SUBTLE  = "#F9ECED"
_SLATE_PRIMARY   = "#4A6FA5"
_SLATE_TEXT      = "#B8D0F0"
_SLATE_DARK      = "#2E4F85"

_ABR_FRAME_STYLE = f"""
    QGroupBox {{
        font-size: 11px;
        font-weight: bold;
        color: {_CRIMSON_DARK};
        border: 2px solid {_CRIMSON_PRIMARY};
        border-radius: 8px;
        margin-top: 3px;
        margin-bottom: 0px;
        padding: 0px;
        background-color: {WHITE};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 1px 10px;
        background-color: {_CRIMSON_PRIMARY};
        color: {_SLATE_TEXT};
        border-radius: 4px;
        left: 10px;
    }}
    QGroupBox QLabel {{
        font-size: 10px;
        color: {GRAY_DARK};
        border: none;
        background: transparent;
    }}
"""

_ABR_LIST_STYLE = f"""
    QListWidget {{
        font-size: 11px;
        border: none;
        background-color: {WHITE};
        outline: none;
        padding: 0px;
        margin: 0px;
    }}
    QListWidget::item {{
        padding: 0px 4px;
        margin: 0px;
        border: none;
        min-height: 0px;
    }}
    QListWidget::item:hover   {{ background-color: {_CRIMSON_SUBTLE}; }}
    QListWidget::item:selected {{ background-color: {_SLATE_PRIMARY}; color: {WHITE}; font-weight: bold; }}
"""

_ABR_NAV_BTN_STYLE = f"""
    QPushButton {{
        background: {_CRIMSON_SUBTLE};
        color: {_CRIMSON_DARK};
        border: 1px solid {_CRIMSON_PRIMARY};
        border-radius: 3px;
        padding: 1px 5px;
        font-size: 11px;
        font-weight: bold;
        min-height: 16px;
        max-height: 18px;
    }}
    QPushButton:hover {{ background: {_CRIMSON_PRIMARY}; color: {WHITE}; }}
    QPushButton:disabled {{ background: {GRAY_LIGHT}; color: {GRAY_MID}; border-color: {GRAY_MID}; }}
"""

_ABR_PATH_BAR_STYLE = f"""
    font-size: 10px;
    color: {_CRIMSON_DARK};
    background: {_CRIMSON_SUBTLE};
    border: 1px solid {_CRIMSON_PRIMARY};
    border-radius: 3px;
    padding: 1px 4px;
"""

_ABR_PATH_LABEL_STYLE = f"""
    font-size: 10px; color: {_CRIMSON_DARK};
    background: {_CRIMSON_SUBTLE};
    border: 1px solid {_CRIMSON_PRIMARY};
    border-radius: 3px; padding: 3px 6px;
"""

_ABR_ACTION_BTN_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {_SLATE_TEXT}, stop:1 {_SLATE_PRIMARY});
        color: {WHITE};
        border: 1px solid {_SLATE_DARK};
        border-radius: 3px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: bold;
        min-height: 18px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {_SLATE_PRIMARY}, stop:1 {_SLATE_DARK});
        color: {WHITE};
    }}
    QPushButton:pressed {{ background-color: {_SLATE_DARK}; }}
    QPushButton:disabled {{
        background: {GRAY_MID}; color: {GRAY_DARK}; border-color: {GRAY_MID};
    }}
"""

_MODE_BTN_ABR_ACTIVE_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {_CRIMSON_RICH}, stop:1 {_CRIMSON_PRIMARY});
        color: {WHITE};
        border: 2px solid {_CRIMSON_DARK};
        border-radius: 4px;
        padding: 4px 16px;
        font-size: 12px;
        font-weight: bold;
        min-height: 22px;
    }}
"""

# Mime type tokens used for drag-and-drop
_MIME_CATEGORY = "application/x-suiteview-category"
_MIME_TOOL_FILE = "application/x-suiteview-toolfile"


# ---------------------------------------------------------------------------
# TightItemDelegate
# ---------------------------------------------------------------------------

class _TightItemDelegate(QStyledItemDelegate):
    ROW_H = 16
    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        return QSize(sh.width(), self.ROW_H)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _icon_for_ext(ext: str) -> str:
    return {
        ".py": "🐍", ".r": "📊", ".R": "📊",
        ".xlsx": "📗", ".xls": "📗", ".xlsm": "📗",
        ".sql": "🗃️", ".vbs": "⚙️", ".bat": "⚙️", ".ps1": "⚙️",
        ".txt": "📝", ".pdf": "📕", ".docx": "📘",
    }.get(ext, "📄")


# ---------------------------------------------------------------------------
# DraggableCategoryList  — Task Categories list with drag support
# ---------------------------------------------------------------------------

class _DraggableCategoryList(QListWidget):
    """QListWidget that starts a drag carrying the category name."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        mime = QMimeData()
        mime.setData(_MIME_CATEGORY, item.text().encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        # Simple drag pixmap
        pix = QPixmap(160, 18)
        pix.fill(QColor(GOLD_LIGHT))
        painter = QPainter(pix)
        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor(GREEN_DARK))
        painter.drawText(4, 13, item.text())
        painter.end()
        drag.setPixmap(pix)
        drag.exec(Qt.DropAction.CopyAction)


# ---------------------------------------------------------------------------
# DraggableToolsList  — Available Tools list with drag support
# ---------------------------------------------------------------------------

class _DraggableToolsList(QListWidget):
    """QListWidget that starts a drag carrying a file path."""

    _PATH_ROLE = Qt.ItemDataRole.UserRole

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        path = item.data(self._PATH_ROLE) or ""
        if not path or not os.path.isfile(path):
            return  # only drag files, not folders
        mime = QMimeData()
        mime.setData(_MIME_TOOL_FILE, path.encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        pix = QPixmap(200, 18)
        pix.fill(QColor(GOLD_LIGHT))
        painter = QPainter(pix)
        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor(GREEN_DARK))
        painter.drawText(4, 13, os.path.basename(path))
        painter.end()
        drag.setPixmap(pix)
        drag.exec(Qt.DropAction.CopyAction)


# ---------------------------------------------------------------------------
# DropTargetSubfolderList  — Policy Subfolders list that accepts drops
# ---------------------------------------------------------------------------

class _DropTargetSubfolderList(QListWidget):
    """QListWidget that accepts drops from categories and tool files."""

    category_dropped = pyqtSignal(str)   # category name
    file_dropped     = pyqtSignal(str)   # source file path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md.hasFormat(_MIME_CATEGORY) or md.hasFormat(_MIME_TOOL_FILE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        md = event.mimeData()
        if md.hasFormat(_MIME_CATEGORY) or md.hasFormat(_MIME_TOOL_FILE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        md = event.mimeData()
        if md.hasFormat(_MIME_CATEGORY):
            name = bytes(md.data(_MIME_CATEGORY)).decode()
            self.category_dropped.emit(name)
            event.acceptProposedAction()
        elif md.hasFormat(_MIME_TOOL_FILE):
            path = bytes(md.data(_MIME_TOOL_FILE)).decode()
            self.file_dropped.emit(path)
            event.acceptProposedAction()
        else:
            event.ignore()


# ---------------------------------------------------------------------------
# MiniExplorer  — reusable mini file-explorer panel
# ---------------------------------------------------------------------------

class MiniExplorer(QWidget):
    """Compact file explorer with Home/Up navigation and path breadcrumb.

    The list widget passed in (via list_widget_class) is used so callers
    can supply a drag-enabled subclass.
    """

    file_selected = pyqtSignal(str)

    _PATH_ROLE = Qt.ItemDataRole.UserRole

    def __init__(self, title: str = "", root_path: str = "",
                 list_widget_class=None, parent=None):
        super().__init__(parent)
        self._root_path = root_path
        self._current_path = root_path
        self._title = title
        self._at_home = True          # True when showing pinned home entries
        self._home_entries: list = [] # [(label, full_path), ...] for home view
        self._list_cls = list_widget_class or QListWidget
        self._setup_ui()

    def _setup_ui(self):
        outer = QGroupBox(self._title)
        outer.setStyleSheet(POLICY_INFO_FRAME_STYLE)
        ol = QVBoxLayout(outer)
        ol.setContentsMargins(2, 14, 2, 2)
        ol.setSpacing(2)

        # Nav bar
        nav = QHBoxLayout()
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(2)

        self._home_btn = QPushButton("⌂")
        self._home_btn.setStyleSheet(_NAV_BTN_STYLE)
        self._home_btn.setFixedWidth(22)
        self._home_btn.setToolTip("Go home")
        self._home_btn.clicked.connect(self._go_home)

        self._up_btn = QPushButton("↑")
        self._up_btn.setStyleSheet(_NAV_BTN_STYLE)
        self._up_btn.setFixedWidth(22)
        self._up_btn.setToolTip("Go up one level")
        self._up_btn.clicked.connect(self._go_up)

        self._path_label = _DoubleClickablePathLabel("")
        self._path_label.setStyleSheet(_PATH_BAR_STYLE)
        self._path_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        nav.addWidget(self._home_btn)
        nav.addWidget(self._up_btn)
        nav.addWidget(self._path_label, 1)
        ol.addLayout(nav)

        # List
        self._list: QListWidget = self._list_cls()
        self._list.setStyleSheet(_LIST_STYLE)
        self._list.setItemDelegate(_TightItemDelegate(self._list))
        self._list.setUniformItemSizes(True)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        self._list.currentItemChanged.connect(self._on_sel_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        ol.addWidget(self._list, 1)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(outer)

    # -- Home entries (pinned folders) -------------------------------------

    def set_home_entries(self, entries: list):
        """Set the list of (label, full_path) tuples shown on the home screen."""
        self._home_entries = entries
        self._go_home()

    # -- Navigation --------------------------------------------------------

    def set_root(self, path: str):
        self._root_path = path
        self._current_path = path
        self._at_home = False
        self._refresh()

    def _go_home(self):
        self._at_home = True
        self._current_path = ""
        self._refresh()

    def _go_up(self):
        """Navigate to the parent directory. Goes home only if already at a filesystem root."""
        if self._at_home:
            return
        if not self._current_path:
            self._go_home()
            return
        parent = os.path.dirname(self._current_path)
        # If dirname returns the same path we're at a filesystem root — go home
        if parent == self._current_path:
            self._go_home()
        else:
            self._current_path = parent
            self._refresh()

    def _on_double_click(self, item: QListWidgetItem):
        """Navigate into a folder (or do nothing for files — files are drag-only)."""
        path = item.data(self._PATH_ROLE)
        if path and os.path.isdir(path):
            self._at_home = False
            self._root_path = path if not self._root_path else self._root_path
            self._current_path = path
            self._refresh()

    def _on_sel_changed(self, current: QListWidgetItem, _prev):
        if not current:
            return
        path = current.data(self._PATH_ROLE) or ""
        if os.path.isfile(path):
            self.file_selected.emit(path)

    def _on_context_menu(self, pos: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet(_CONTEXT_MENU_STYLE)
        up_act = menu.addAction("↑  Go Up")
        up_act.setEnabled(not self._at_home)
        home_act = menu.addAction("⌂  Go Home")
        home_act.setEnabled(not self._at_home and bool(self._home_entries))

        item = self._list.itemAt(pos)
        open_act = None
        if item:
            path = item.data(self._PATH_ROLE) or ""
            if os.path.isdir(path):
                menu.addSeparator()
                open_act = menu.addAction("Open in Explorer")

        action = menu.exec(self._list.viewport().mapToGlobal(pos))
        if action is up_act:
            self._go_up()
        elif action is home_act:
            self._go_home()
        elif action is open_act and item:
            path = item.data(self._PATH_ROLE) or ""
            if os.path.exists(path):
                os.startfile(path)

    # -- Rendering ---------------------------------------------------------

    def _refresh(self):
        self._list.clear()
        self._up_btn.setEnabled(not self._at_home)
        self._home_btn.setEnabled(not self._at_home and bool(self._home_entries))

        if self._at_home:
            self._path_label.setText("Home")
            self._path_label.set_open_path("")  # nothing to open at home
            for label, full_path in self._home_entries:
                exists = os.path.isdir(full_path)
                icon = "📁" if exists else "⚠️"
                item = QListWidgetItem(f"{icon}  {label}")
                item.setData(self._PATH_ROLE, full_path)
                if not exists:
                    item.setForeground(QColor(GRAY_MID))
                    item.setToolTip("Folder not found")
                self._list.addItem(item)
            return

        self._update_path_label()
        if not self._current_path or not os.path.isdir(self._current_path):
            return

        try:
            entries = sorted(
                os.listdir(self._current_path),
                key=lambda e: (
                    not os.path.isdir(os.path.join(self._current_path, e)),
                    e.lower()
                )
            )
            for entry in entries:
                full = os.path.join(self._current_path, entry)
                if os.path.isdir(full):
                    item = QListWidgetItem(f"📁  {entry}")
                else:
                    ext = os.path.splitext(entry)[1].lower()
                    item = QListWidgetItem(f"{_icon_for_ext(ext)}  {entry}")
                item.setData(self._PATH_ROLE, full)
                self._list.addItem(item)
        except Exception as e:
            self._list.addItem(QListWidgetItem(f"(Error: {e})"))

    def _update_path_label(self):
        if not self._current_path:
            self._path_label.setText("")
            self._path_label.set_open_path("")
            return
        # Show last 2 path components for compactness; full path stored for open
        try:
            parts = self._current_path.replace("\\", "/").split("/")
            rel = "\\".join(parts[-2:]) if len(parts) >= 2 else self._current_path
        except Exception:
            rel = self._current_path
        self._path_label.setText(rel)
        self._path_label.set_open_path(self._current_path)

    # -- Public helpers ----------------------------------------------------

    def current_path(self) -> str:
        return self._current_path if not self._at_home else ""

    def selected_file_path(self) -> str:
        item = self._list.currentItem()
        if not item:
            return ""
        path = item.data(self._PATH_ROLE) or ""
        return path if os.path.isfile(path) else ""

    def refresh(self):
        self._refresh()


# ---------------------------------------------------------------------------
# _DoubleClickablePathLabel  — QLabel that opens a folder in Explorer on dbl-click
# ---------------------------------------------------------------------------

class _DoubleClickablePathLabel(QLabel):
    """Path-bar label that opens its associated folder in Windows Explorer on double-click.

    The displayed text may be a short/relative form; call set_open_path() to
    store the full absolute path that will actually be opened.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._open_path: str = ""
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_open_path(self, path: str):
        """Set the full path that will be opened on double-click."""
        self._open_path = path
        if path:
            self.setToolTip(f"Double-click to open in Explorer:\n{path}")
        else:
            self.setToolTip("")

    def mouseDoubleClickEvent(self, event):
        path = self._open_path or self.text().strip()
        if path and os.path.isdir(path):
            os.startfile(path)
        super().mouseDoubleClickEvent(event)


# ---------------------------------------------------------------------------
# PolicySupportTab
# ---------------------------------------------------------------------------

class PolicySupportTab(QWidget):
    """Policy Support tab with drag-and-drop workflow.

    - Drag a Task Category → drop on Policy Subfolders → creates that folder
    - Drag a file from Available Tools → drop on Policy Subfolders → copies the file
    - Folders from Available Tools cannot be dragged (only files)
    """

    folder_opened = pyqtSignal(str)

    # Mode constants
    MODE_POLICY_SUPPORT = "policy_support"
    MODE_ABR = "abr"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: Optional['PolicyInformation'] = None
        self._policy_support_folder_path = ""
        self._policy_library_path = ""
        self._user_tasks: List[str] = _load_user_tasks()
        self._current_mode = self.MODE_POLICY_SUPPORT
        self._setup_ui()

    # -- UI ----------------------------------------------------------------

    def _setup_ui(self):
        self.setStyleSheet(f"background-color: {WHITE};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # ── Mode toggle buttons + Top info bar (same row) ─────────────────
        self._btn_mode_polsup = QPushButton("Policy Support")
        self._btn_mode_polsup.setStyleSheet(_MODE_BTN_ACTIVE_STYLE)
        self._btn_mode_polsup.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_mode_polsup.clicked.connect(lambda: self._set_mode(self.MODE_POLICY_SUPPORT))

        self._btn_mode_abr = QPushButton("ABR")
        self._btn_mode_abr.setStyleSheet(_MODE_BTN_INACTIVE_STYLE)
        self._btn_mode_abr.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_mode_abr.clicked.connect(lambda: self._set_mode(self.MODE_ABR))

        # Stack buttons vertically on the left
        btn_col = QVBoxLayout()
        btn_col.setContentsMargins(0, 0, 0, 0)
        btn_col.setSpacing(4)
        btn_col.addStretch(1)
        btn_col.addWidget(self._btn_mode_polsup)
        btn_col.addWidget(self._btn_mode_abr)
        btn_col.addStretch(1)

        # ── Top info bar ──────────────────────────────────────────────────
        self._info_frame = QGroupBox("Policy Support")
        self._info_frame.setStyleSheet(POLICY_INFO_FRAME_STYLE)
        ig = QGridLayout(self._info_frame)
        ig.setContentsMargins(8, 20, 8, 6)
        ig.setHorizontalSpacing(8)
        ig.setVerticalSpacing(4)

        lbl_s = (f"font-size: 11px; font-weight: bold; color: {GREEN_DARK}; "
                 f"background: transparent; border: none;")
        val_s = (f"font-size: 11px; color: {GRAY_DARK}; background: transparent; "
                 f"border: none;")

        ig.addWidget(self._mk_lbl("Policy Folder:", lbl_s), 0, 0)
        self._policy_folder_label = QLabel("No policy loaded")
        self._policy_folder_label.setStyleSheet(val_s)
        ig.addWidget(self._policy_folder_label, 0, 1)

        # OneDrive / SharePoint warning — shown when Process_Control folder is missing
        self._onedrive_warning_label = QLabel(
            "⚠️  SharePoint library not linked to OneDrive.\n"
            "To use Policy Support, sync the 'Life Product - Process_Control'\n"
            "library to your OneDrive."
        )
        self._onedrive_warning_label.setStyleSheet(
            "font-size: 10px; font-weight: bold; color: #7B3F00; "
            "background: #FFF3CD; border: 1px solid #FFC107; "
            "border-radius: 4px; padding: 4px 8px;"
        )
        self._onedrive_warning_label.setWordWrap(True)
        self._onedrive_warning_label.setVisible(False)
        ig.addWidget(self._onedrive_warning_label, 0, 2, 2, 1)  # span rows 0–1

        ig.addWidget(self._mk_lbl("Library Path:", lbl_s), 1, 0)
        self._library_path_label = _DoubleClickablePathLabel("")
        self._library_path_label.setStyleSheet(_PATH_LABEL_STYLE)
        self._library_path_label.setWordWrap(True)
        self._library_path_label.setToolTip("Double-click to open in Explorer")
        ig.addWidget(self._library_path_label, 1, 1)

        ig.addWidget(self._mk_lbl("Status:", lbl_s), 2, 0)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(_STATUS_STYLE)
        ig.addWidget(self._status_label, 2, 1)

        self._create_folder_btn = QPushButton("📁  Create Policy Folder")
        self._create_folder_btn.setStyleSheet(_ACTION_BTN_STYLE)
        self._create_folder_btn.clicked.connect(self._on_create_policy_folder)
        self._create_folder_btn.setVisible(False)
        ig.addWidget(self._create_folder_btn, 2, 2)

        ig.setColumnStretch(1, 1)

        # Combine buttons + info group in one row
        info_row = QHBoxLayout()
        info_row.setContentsMargins(8, 0, 0, 0)
        info_row.setSpacing(6)
        info_row.addLayout(btn_col)
        info_row.addWidget(self._info_frame, 1)
        layout.addLayout(info_row)

        # Check OneDrive linkage immediately so the warning shows even before a policy loads
        self._check_onedrive()

        # ── Hint bar ──────────────────────────────────────────────────────
        hint = QLabel(
            "💡  Drag a category → Policy Subfolders to create a task folder  |  "
            "Drag a file from Available Tools → Policy Subfolders to copy it"
        )
        hint.setStyleSheet(
            f"font-size: 10px; color: {GRAY_DARK}; background: transparent; "
            f"border: none; padding: 0px 2px;"
        )
        layout.addWidget(hint)

        # ── Three-column middle ───────────────────────────────────────────
        cols = QWidget()
        cl = QHBoxLayout(cols)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)

        # Column 1 — Task Categories (draggable)
        self._cat_frame = QGroupBox("Task Categories")
        self._cat_frame.setStyleSheet(POLICY_INFO_FRAME_STYLE)
        cat_fl = QVBoxLayout(self._cat_frame)
        cat_fl.setContentsMargins(2, 14, 2, 2)
        cat_fl.setSpacing(0)

        self._category_list = _DraggableCategoryList()
        self._category_list.setStyleSheet(_LIST_STYLE)
        self._category_list.setItemDelegate(_TightItemDelegate(self._category_list))
        self._category_list.setUniformItemSizes(True)
        self._category_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._category_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._category_list.customContextMenuRequested.connect(self._on_category_context_menu)
        cat_fl.addWidget(self._category_list)

        cl.addWidget(self._cat_frame, 2)

        # Column 2 — Policy Subfolders (drop target + mini explorer)
        sub_col = QVBoxLayout()
        sub_col.setSpacing(0)

        # Drop-target list at the top (shows current subfolder contents)
        self._subfolder_explorer = _SubfolderExplorer(title="Policy Subfolders")
        self._subfolder_explorer.category_dropped.connect(self._on_category_dropped)
        self._subfolder_explorer.file_dropped.connect(self._on_file_dropped)
        sub_col.addWidget(self._subfolder_explorer, 1)
        cl.addLayout(sub_col, 3)

        # Column 3 — Available Tools (draggable mini explorer)
        self._tools_explorer = MiniExplorer(
            title="Available Tools",
            list_widget_class=_DraggableToolsList,
        )
        # Build home entries: process-control-relative folders + absolute folders
        pc = _get_process_control_dir()
        home_entries = [
            (label, os.path.join(pc, rel_path))
            for label, rel_path in TOOL_FOLDERS
        ]
        home_entries += list(_ABS_TOOL_FOLDERS)
        self._tools_explorer.set_home_entries(home_entries)
        cl.addWidget(self._tools_explorer, 3)

        layout.addWidget(cols, 1)

    @staticmethod
    def _mk_lbl(text: str, style: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(style)
        return l

    # -- OneDrive check ----------------------------------------------------

    def _check_onedrive(self) -> bool:
        """Check if the Process_Control SharePoint library is synced to OneDrive.

        Shows a warning label inside this tab if not found.
        Returns True if the folder exists, False otherwise.
        Note: this only affects the Policy Support tab — the rest of PolView
        works fine without the OneDrive link.
        """
        exists = os.path.isdir(_get_process_control_dir())
        self._onedrive_warning_label.setVisible(not exists)
        # Hide library path row when there's nothing useful to show
        self._library_path_label.setVisible(exists)
        return exists

    # -- Data loading -------------------------------------------------------

    def load_data_from_policy(self, policy: 'PolicyInformation'):
        self._policy = policy

        if not policy or not policy.exists:
            self._policy_folder_label.setText("No policy loaded")
            self._library_path_label.setText("")
            self._status_label.setText("")
            self._create_folder_btn.setVisible(False)
            self._category_list.clear()
            self._subfolder_explorer.set_root("")
            return

        # Bail out early if the SharePoint library isn't synced to OneDrive.
        # The rest of PolView works fine without it — only this tab needs it.
        if not self._check_onedrive():
            self._policy_folder_label.setText("")
            self._library_path_label.setText("")
            self._status_label.setText("")
            self._create_folder_btn.setVisible(False)
            self._subfolder_explorer.set_root("")
            return

        # Populate categories (disabled in ABR mode)
        if self._current_mode == self.MODE_ABR:
            self._category_list.clear()
            self._category_list.setEnabled(False)
        else:
            self._category_list.setEnabled(True)
            self._populate_category_list()

        product_type = policy.product_type
        company_code = policy.company_code
        policy_number = policy.policy_number

        if self._current_mode == self.MODE_ABR:
            # ABR mode: point to the ABR Policies folder
            abr_dir = _get_abr_dir()
            self._policy_library_path = os.path.join(abr_dir, "Policies")
            self._policy_support_folder_path = os.path.join(
                self._policy_library_path, policy_number
            )
        else:
            # Policy Support mode: original behavior
            ps_dir = _get_policy_support_dir()
            self._policy_library_path = os.path.join(ps_dir, "POLICY_LIBRARY", product_type)
            self._policy_support_folder_path = os.path.join(
                self._policy_library_path, f"{company_code}_{policy_number}"
            )

        self._library_path_label.setText(self._policy_library_path)
        folder_exists = os.path.isdir(self._policy_support_folder_path)

        if folder_exists:
            folder_name = policy_number if self._current_mode == self.MODE_ABR else f"{company_code}_{policy_number}"
            self._policy_folder_label.setText(folder_name)
            self._policy_folder_label.setStyleSheet(
                f"font-size: 11px; color: {GREEN_DARK}; font-weight: bold; "
                f"background: transparent; border: none;"
            )
            self._create_folder_btn.setVisible(False)
            self._status_label.setText("✓ Policy folder exists")
            self._status_label.setStyleSheet(
                f"font-size: 10px; color: {GREEN_DARK}; font-weight: bold; "
                f"background: transparent; border: none;"
            )
            self._subfolder_explorer.set_root(self._policy_support_folder_path)
        else:
            self._policy_folder_label.setText("No Folder Found")
            self._policy_folder_label.setStyleSheet(
                f"font-size: 11px; color: #C00000; font-weight: bold; "
                f"background: transparent; border: none;"
            )
            self._create_folder_btn.setVisible(True)
            self._status_label.setText(
                "Policy folder does not exist — drag a category here or click Create"
            )
            self._status_label.setStyleSheet(
                f"font-size: 10px; color: {GOLD_DARK}; "
                f"background: transparent; border: none;"
            )
            self._subfolder_explorer.set_root("")

    # -- Mode switching -----------------------------------------------------

    def _set_mode(self, mode: str):
        """Switch between Policy Support and ABR modes."""
        if mode == self._current_mode:
            return
        self._current_mode = mode

        # Update button visuals + theme
        if mode == self.MODE_POLICY_SUPPORT:
            self._btn_mode_polsup.setStyleSheet(_MODE_BTN_ACTIVE_STYLE)
            self._btn_mode_abr.setStyleSheet(_MODE_BTN_INACTIVE_STYLE)
            self._info_frame.setTitle("Policy Support")
            self._apply_green_theme()
        else:
            self._btn_mode_polsup.setStyleSheet(_MODE_BTN_INACTIVE_STYLE)
            self._btn_mode_abr.setStyleSheet(_MODE_BTN_ABR_ACTIVE_STYLE)
            self._info_frame.setTitle("ABR Policy Support")
            self._apply_abr_theme()

        # Reload data with the new mode
        if self._policy:
            self.load_data_from_policy(self._policy)

    def _apply_green_theme(self):
        """Restore the default green/gold Policy Support theme to all 4 group panels."""
        # 1. Info frame
        self._info_frame.setStyleSheet(POLICY_INFO_FRAME_STYLE)
        self._library_path_label.setStyleSheet(_PATH_LABEL_STYLE)
        self._create_folder_btn.setStyleSheet(_ACTION_BTN_STYLE)

        # 2. Task Categories
        self._cat_frame.setStyleSheet(POLICY_INFO_FRAME_STYLE)
        self._category_list.setStyleSheet(_LIST_STYLE)

        # 3. Policy Subfolders
        self._apply_explorer_theme(
            self._subfolder_explorer,
            POLICY_INFO_FRAME_STYLE, _LIST_STYLE, _NAV_BTN_STYLE, _PATH_BAR_STYLE,
        )

        # 4. Available Tools
        self._apply_explorer_theme(
            self._tools_explorer,
            POLICY_INFO_FRAME_STYLE, _LIST_STYLE, _NAV_BTN_STYLE, _PATH_BAR_STYLE,
        )

    def _apply_abr_theme(self):
        """Apply the crimson/slate ABR theme to all 4 group panels."""
        # 1. Info frame
        self._info_frame.setStyleSheet(_ABR_FRAME_STYLE)
        self._library_path_label.setStyleSheet(_ABR_PATH_LABEL_STYLE)
        self._create_folder_btn.setStyleSheet(_ABR_ACTION_BTN_STYLE)

        # 2. Task Categories
        self._cat_frame.setStyleSheet(_ABR_FRAME_STYLE)
        self._category_list.setStyleSheet(_ABR_LIST_STYLE)

        # 3. Policy Subfolders
        self._apply_explorer_theme(
            self._subfolder_explorer,
            _ABR_FRAME_STYLE, _ABR_LIST_STYLE, _ABR_NAV_BTN_STYLE, _ABR_PATH_BAR_STYLE,
        )

        # 4. Available Tools
        self._apply_explorer_theme(
            self._tools_explorer,
            _ABR_FRAME_STYLE, _ABR_LIST_STYLE, _ABR_NAV_BTN_STYLE, _ABR_PATH_BAR_STYLE,
        )

    @staticmethod
    def _apply_explorer_theme(explorer, frame_style, list_style, nav_style, path_style):
        """Apply a theme to a MiniExplorer or _SubfolderExplorer widget."""
        # Group box
        gb = explorer.findChild(QGroupBox)
        if gb:
            gb.setStyleSheet(frame_style)
        # Nav buttons
        if hasattr(explorer, '_home_btn'):
            explorer._home_btn.setStyleSheet(nav_style)
        if hasattr(explorer, '_up_btn'):
            explorer._up_btn.setStyleSheet(nav_style)
        # Path label
        if hasattr(explorer, '_path_label'):
            explorer._path_label.setStyleSheet(path_style)
        # List widget
        if hasattr(explorer, '_list'):
            explorer._list.setStyleSheet(list_style)

    # -- Category helpers --------------------------------------------------

    def _all_categories(self) -> List[str]:
        return sorted(set(DEFAULT_TASK_CATEGORIES) | set(self._user_tasks))

    def _populate_category_list(self):
        self._category_list.clear()
        for cat in self._all_categories():
            item = QListWidgetItem(cat)
            if cat in self._user_tasks:
                item.setForeground(QColor(GOLD_DARK))
            self._category_list.addItem(item)

    # -- Category context menu ---------------------------------------------

    def _on_category_context_menu(self, pos: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet(_CONTEXT_MENU_STYLE)
        add_action = menu.addAction("Add New Task Category...")

        item = self._category_list.itemAt(pos)
        sel_name = item.text() if item else ""
        is_user = sel_name in self._user_tasks

        rename_action = delete_action = None
        if sel_name:
            menu.addSeparator()
            rename_action = menu.addAction(f"Rename '{sel_name}'...")
            delete_action = menu.addAction(f"Delete '{sel_name}'")
            if not is_user:
                rename_action.setEnabled(False)
                delete_action.setEnabled(False)
                rename_action.setToolTip("Cannot modify default categories")
                delete_action.setToolTip("Cannot delete default categories")

        action = menu.exec(self._category_list.viewport().mapToGlobal(pos))
        if action is add_action:
            self._add_task_category()
        elif action is rename_action and sel_name:
            self._rename_task_category(sel_name)
        elif action is delete_action and sel_name:
            self._delete_task_category(sel_name)

    def _add_task_category(self):
        name, ok = QInputDialog.getText(
            self, "Add Task Category",
            "Enter new task category name\n(use underscores for spaces):",
        )
        if not ok or not name.strip():
            return
        name = name.strip().replace(" ", "_")
        if name in self._all_categories():
            QMessageBox.information(self, "Duplicate", f"'{name}' already exists.")
            return
        self._user_tasks.append(name)
        _save_user_tasks(self._user_tasks)
        self._populate_category_list()
        self._status_label.setText(f"✓ Added task category: {name}")

    def _rename_task_category(self, old_name: str):
        new_name, ok = QInputDialog.getText(
            self, "Rename Task Category", f"Rename '{old_name}' to:", text=old_name
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip().replace(" ", "_")
        if new_name in self._all_categories():
            QMessageBox.information(self, "Duplicate", f"'{new_name}' already exists.")
            return
        self._user_tasks = [new_name if t == old_name else t for t in self._user_tasks]
        _save_user_tasks(self._user_tasks)
        self._populate_category_list()
        self._status_label.setText(f"✓ Renamed '{old_name}' → '{new_name}'")

    def _delete_task_category(self, name: str):
        reply = QMessageBox.question(
            self, "Delete Task Category",
            f"Delete '{name}' from the task list?\n\n(This does not delete any folders on disk.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._user_tasks = [t for t in self._user_tasks if t != name]
        _save_user_tasks(self._user_tasks)
        self._populate_category_list()
        self._status_label.setText(f"✓ Removed task category: {name}")

    # -- Drop handlers -----------------------------------------------------

    def _on_category_dropped(self, category_name: str):
        """A category was dragged onto the Policy Subfolders panel."""
        dest_dir = self._subfolder_explorer.current_path()
        if not dest_dir:
            dest_dir = self._policy_support_folder_path

        if not dest_dir:
            QMessageBox.information(self, "No Policy Folder",
                                    "Load a policy first.")
            return

        task_folder = os.path.join(dest_dir, category_name)
        if os.path.isdir(task_folder):
            self._status_label.setText(f"ℹ️  '{category_name}' folder already exists")
            return

        try:
            # Auto-create policy folder if needed
            if not os.path.isdir(self._policy_support_folder_path):
                os.makedirs(self._policy_support_folder_path, exist_ok=True)
                self._subfolder_explorer.set_root(self._policy_support_folder_path)
                self._create_folder_btn.setVisible(False)
                if self._policy:
                    cc, pn = self._policy.company_code, self._policy.policy_number
                    self._policy_folder_label.setText(f"{cc}_{pn}")
                    self._policy_folder_label.setStyleSheet(
                        f"font-size: 11px; color: {GREEN_DARK}; font-weight: bold; "
                        f"background: transparent; border: none;"
                    )

            os.makedirs(task_folder, exist_ok=True)
            self._status_label.setText(f"✓ Created task folder: {category_name}")
            self._status_label.setStyleSheet(
                f"font-size: 10px; color: {GREEN_DARK}; font-weight: bold; "
                f"background: transparent; border: none;"
            )
            self._subfolder_explorer.refresh()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to create folder:\n{e}")

    def _on_file_dropped(self, source_path: str):
        """A tool file was dragged onto the Policy Subfolders panel."""
        if not source_path or not os.path.isfile(source_path):
            return

        dest_dir = self._subfolder_explorer.current_path()
        if not dest_dir or not os.path.isdir(dest_dir):
            QMessageBox.information(
                self, "No Destination",
                "Please navigate into a subfolder in Policy Subfolders first."
            )
            return

        filename = os.path.basename(source_path)
        if self._policy:
            dest_filename = f"{self._policy.policy_number} - {filename}"
        else:
            dest_filename = filename

        dest_path = os.path.join(dest_dir, dest_filename)
        if os.path.exists(dest_path):
            QMessageBox.information(
                self, "File Exists",
                f"'{dest_filename}' already exists here.\nOperation cancelled."
            )
            return

        try:
            shutil.copy2(source_path, dest_path)
            self._status_label.setText(f"✓ Copied: {dest_filename}")
            self._status_label.setStyleSheet(
                f"font-size: 10px; color: {GREEN_DARK}; font-weight: bold; "
                f"background: transparent; border: none;"
            )
            self._subfolder_explorer.refresh()
        except Exception as e:
            QMessageBox.warning(self, "Copy Error", f"Failed to copy file:\n{e}")

    # -- Policy folder actions ---------------------------------------------

    def _on_create_policy_folder(self):
        if not self._policy_support_folder_path:
            return
        try:
            os.makedirs(self._policy_support_folder_path, exist_ok=True)
            self._status_label.setText("✓ Policy folder created")
            self._status_label.setStyleSheet(
                f"font-size: 10px; color: {GREEN_DARK}; font-weight: bold; "
                f"background: transparent; border: none;"
            )
            self._create_folder_btn.setVisible(False)
            if self._policy:
                cc, pn = self._policy.company_code, self._policy.policy_number
                self._policy_folder_label.setText(f"{cc}_{pn}")
                self._policy_folder_label.setStyleSheet(
                    f"font-size: 11px; color: {GREEN_DARK}; font-weight: bold; "
                    f"background: transparent; border: none;"
                )
            self._subfolder_explorer.set_root(self._policy_support_folder_path)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to create policy folder:\n{e}")



# ---------------------------------------------------------------------------
# _SubfolderExplorer  — Policy Subfolders panel (drop target + mini explorer)
# ---------------------------------------------------------------------------

class _SubfolderExplorer(QWidget):
    """Mini explorer for the policy folder that also accepts drag-and-drop."""

    category_dropped = pyqtSignal(str)
    file_dropped     = pyqtSignal(str)

    _PATH_ROLE = Qt.ItemDataRole.UserRole

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self._root_path = ""
        self._current_path = ""
        self._title = title
        self._setup_ui()

    def _setup_ui(self):
        outer = QGroupBox(self._title)
        outer.setStyleSheet(POLICY_INFO_FRAME_STYLE)
        ol = QVBoxLayout(outer)
        ol.setContentsMargins(2, 14, 2, 2)
        ol.setSpacing(2)

        # Nav bar
        nav = QHBoxLayout()
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(2)

        self._home_btn = QPushButton("⌂")
        self._home_btn.setStyleSheet(_NAV_BTN_STYLE)
        self._home_btn.setFixedWidth(22)
        self._home_btn.setToolTip("Go to policy root folder")
        self._home_btn.clicked.connect(self._go_home)

        self._up_btn = QPushButton("↑")
        self._up_btn.setStyleSheet(_NAV_BTN_STYLE)
        self._up_btn.setFixedWidth(22)
        self._up_btn.setToolTip("Go up one level")
        self._up_btn.clicked.connect(self._go_up)

        self._path_label = _DoubleClickablePathLabel("")
        self._path_label.setStyleSheet(_PATH_BAR_STYLE)
        self._path_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        nav.addWidget(self._home_btn)
        nav.addWidget(self._up_btn)
        nav.addWidget(self._path_label, 1)
        ol.addLayout(nav)

        self._list = _DropTargetSubfolderList()
        self._list.setStyleSheet(_LIST_STYLE)
        self._list.setItemDelegate(_TightItemDelegate(self._list))
        self._list.setUniformItemSizes(True)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        # Wire drop signals
        self._list.category_dropped.connect(self.category_dropped)
        self._list.file_dropped.connect(self.file_dropped)
        ol.addWidget(self._list, 1)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(outer)

    def set_root(self, path: str):
        self._root_path = path
        self._current_path = path
        self._refresh()

    def _go_home(self):
        if self._root_path:
            self._current_path = self._root_path
            self._refresh()

    def _go_up(self):
        if not self._root_path or not self._current_path:
            return
        parent = os.path.dirname(self._current_path)
        root_norm = os.path.normpath(self._root_path)
        if os.path.normpath(parent).startswith(root_norm):
            self._current_path = parent
            self._refresh()

    def _on_double_click(self, item: QListWidgetItem):
        path = item.data(self._PATH_ROLE) or ""
        if os.path.isdir(path):
            self._current_path = path
            self._refresh()
        elif os.path.isfile(path):
            os.startfile(path)

    def _on_context_menu(self, pos: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet(_CONTEXT_MENU_STYLE)

        can_up = (bool(self._root_path) and bool(self._current_path) and
                  os.path.normpath(self._current_path) != os.path.normpath(self._root_path))
        up_act = menu.addAction("↑  Go Up")
        up_act.setEnabled(can_up)
        home_act = menu.addAction("⌂  Go to Policy Root")
        home_act.setEnabled(can_up)

        item = self._list.itemAt(pos)
        open_act = rename_act = delete_act = None
        entry_name = ""
        if item:
            path = item.data(self._PATH_ROLE) or ""
            entry_name = os.path.basename(path)
            if entry_name:
                menu.addSeparator()
                open_act = menu.addAction(f"Open '{entry_name}'")
                rename_act = menu.addAction(f"Rename '{entry_name}'...")
                delete_act = menu.addAction(f"Delete '{entry_name}'")

        action = menu.exec(self._list.viewport().mapToGlobal(pos))
        if action is up_act:
            self._go_up()
        elif action is home_act:
            self._go_home()
        elif action is open_act and entry_name:
            path = item.data(self._PATH_ROLE) or ""
            if os.path.exists(path):
                os.startfile(path)
        elif action is rename_act and entry_name:
            self._rename_entry(item)
        elif action is delete_act and entry_name:
            self._delete_entry(item)

    def _rename_entry(self, item: QListWidgetItem):
        path = item.data(self._PATH_ROLE) or ""
        old_name = os.path.basename(path)
        new_name, ok = QInputDialog.getText(
            self, "Rename", f"Rename '{old_name}' to:", text=old_name
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_path = os.path.join(os.path.dirname(path), new_name.strip())
        if os.path.exists(new_path):
            QMessageBox.information(self, "Exists", f"'{new_name}' already exists.")
            return
        try:
            os.rename(path, new_path)
            self._refresh()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to rename:\n{e}")

    def _delete_entry(self, item: QListWidgetItem):
        path = item.data(self._PATH_ROLE) or ""
        name = os.path.basename(path)
        is_dir = os.path.isdir(path)
        kind = "folder" if is_dir else "file"
        reply = QMessageBox.question(
            self, f"Delete {kind.title()}",
            f"Permanently delete {kind} '{name}'?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            if is_dir:
                shutil.rmtree(path)
            else:
                os.remove(path)
            self._refresh()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to delete:\n{e}")

    def _refresh(self):
        self._list.clear()
        can_up = (bool(self._root_path) and bool(self._current_path) and
                  os.path.normpath(self._current_path) != os.path.normpath(self._root_path or ""))
        self._up_btn.setEnabled(can_up)
        self._home_btn.setEnabled(can_up)

        if not self._current_path:
            self._path_label.setText("(no policy folder)")
            self._path_label.set_open_path("")
            return

        # Show path relative to root; store full path for double-click open
        try:
            rel = os.path.relpath(self._current_path, os.path.dirname(self._root_path))
        except ValueError:
            rel = self._current_path
        self._path_label.setText(rel)
        self._path_label.set_open_path(self._current_path)

        if not os.path.isdir(self._current_path):
            return

        try:
            entries = sorted(
                os.listdir(self._current_path),
                key=lambda e: (
                    not os.path.isdir(os.path.join(self._current_path, e)),
                    e.lower()
                )
            )
            for entry in entries:
                full = os.path.join(self._current_path, entry)
                if os.path.isdir(full):
                    item = QListWidgetItem(f"📁  {entry}")
                else:
                    ext = os.path.splitext(entry)[1].lower()
                    item = QListWidgetItem(f"{_icon_for_ext(ext)}  {entry}")
                item.setData(self._PATH_ROLE, full)
                self._list.addItem(item)
        except Exception as e:
            self._list.addItem(QListWidgetItem(f"(Error: {e})"))

    def current_path(self) -> str:
        return self._current_path

    def refresh(self):
        self._refresh()
