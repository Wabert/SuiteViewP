"""
Output Panel — File management for ABR Quote policies.

Provides a file explorer interface for the specific policy folder and
relevant tools, similar to PolView's Policy Support tab but simplified.
"""

import logging
import os
from typing import Optional, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QMessageBox, QListWidget, QListWidgetItem,
    QAbstractItemView
)
from PyQt6.QtCore import Qt, QPoint, QMimeData
from PyQt6.QtGui import QColor, QDrag, QPixmap, QPainter, QFont

from suiteview.ui.widgets.mini_explorer import (
    MiniExplorer, DropTargetSubfolderList, DraggableToolsList,
    DoubleClickablePathLabel, TightItemDelegate, icon_for_ext
)
from .abr_styles import (
    CRIMSON_DARK, CRIMSON_PRIMARY, CRIMSON_SUBTLE, SLATE_PRIMARY, SLATE_TEXT, SLATE_DARK, SLATE_LIGHT,
    WHITE, GRAY_DARK, GRAY_MID,
)
from ..models.abr_data import ABRPolicyData, ABRQuoteResult, MedicalAssessment
from ...utils.excel_template import copy_as_workbook, workbook_filename
from suiteview.core.access_control import (
    can_write_support_files, guard_support_files_writable,
)
from suiteview.core.support_files import onedrive_directory, abr_support_directory
logger = logging.getLogger(__name__)

# ── Custom styles for MiniExplorer components (matching ABR theme) ────────────────
ABR_EXPLORER_BOX_STYLE = f"""
    QGroupBox {{
        font-weight: bold;
        border: 2px solid {CRIMSON_PRIMARY};
        border-radius: 8px;
        margin-top: 24px;
        background-color: {WHITE};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 2px 8px;
        color: {SLATE_TEXT};
        background: {CRIMSON_PRIMARY};
        border-radius: 4px;
    }}
"""

ABR_NAV_BTN_STYLE = f"""
    QPushButton {{
        background: {CRIMSON_SUBTLE};
        color: {CRIMSON_DARK};
        border: 1px solid {CRIMSON_PRIMARY};
        border-radius: 3px;
        padding: 1px 5px;
        font-size: 11px;
        font-weight: bold;
        min-height: 16px;
        max-height: 18px;
    }}
    QPushButton:hover {{
        background: {CRIMSON_PRIMARY};
        color: {WHITE};
    }}
    QPushButton:disabled {{
        background: {GRAY_MID};
        color: {GRAY_DARK};
        border-color: {GRAY_MID};
    }}
"""

# Makes path labels "light red" (using CRIMSON_BG/CRIMSON_SUBTLE blend)
ABR_PATH_BAR_STYLE = f"""
    font-size: 10px;
    color: {CRIMSON_DARK};
    background: #F9E0E3;
    border: 1px solid {CRIMSON_PRIMARY};
    border-radius: 3px;
    padding: 1px 4px;
"""

ABR_LIST_STYLE = f"""
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
        color: {GRAY_DARK};
    }}
    QListWidget::item:hover {{
        background-color: {CRIMSON_SUBTLE};
    }}
    QListWidget::item:selected {{
        background-color: {SLATE_LIGHT};
        color: {CRIMSON_DARK};
        font-weight: bold;
    }}
"""

POLICY_INFO_FRAME_STYLE_ABR = f"""
    QGroupBox {{
        font-weight: bold;
        border: 2px solid {CRIMSON_PRIMARY};
        border-radius: 8px;
        margin-top: 10px;
        background-color: {WHITE};
        font-size: 12px;
        color: {CRIMSON_DARK};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        padding: 2px 12px;
        background-color: {CRIMSON_PRIMARY};
        color: {SLATE_TEXT};
        border-radius: 4px;
    }}
"""


# ── Custom List Classes for Drag Styling ─────────────────────────────

# Duplicate MIME constant from mini_explorer to ensure compatibility
_MIME_TOOL_FILE = "application/x-suiteview-toolfile"

class CrimsonDraggableToolsList(DraggableToolsList):
    """Overrides drag image to use Crimson/Slate theme."""
    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        # Access role via Qt.ItemDataRole.UserRole (which MiniExplorer.PATH_ROLE maps to)
        path = item.data(Qt.ItemDataRole.UserRole) or ""
        if not path or not os.path.isfile(path):
            return
        
        mime = QMimeData()
        mime.setData(_MIME_TOOL_FILE, path.encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        
        # Create themed drag pixmap
        pix = QPixmap(200, 20)
        pix.fill(QColor(CRIMSON_SUBTLE)) # Pinkish background
        
        painter = QPainter(pix)
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.setPen(QColor(CRIMSON_DARK)) # Crimson text
        
        # Draw border
        painter.setPen(QColor(CRIMSON_PRIMARY))
        painter.drawRect(0, 0, 199, 19)
        
        painter.setPen(QColor(CRIMSON_DARK))
        # Draw text centered vertically
        rect = pix.rect().adjusted(4, 0, -4, 0)
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, 
                         os.path.basename(path))
        painter.end()
        
        drag.setPixmap(pix)
        drag.setHotSpot(QPoint(10, 10))
        drag.exec(Qt.DropAction.CopyAction)

class CrimsonDropTargetList(DropTargetSubfolderList):
    """Overrides drag image to use Crimson/Slate theme."""
    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole) or ""
        if not path or not os.path.isfile(path):
            return
            
        mime = QMimeData()
        mime.setData(_MIME_TOOL_FILE, path.encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        
        pix = QPixmap(200, 20)
        pix.fill(QColor(CRIMSON_SUBTLE))
        
        painter = QPainter(pix)
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.setPen(QColor(CRIMSON_PRIMARY)) # Border
        painter.drawRect(0, 0, 199, 19)
        
        painter.setPen(QColor(CRIMSON_DARK)) # Text
        rect = pix.rect().adjusted(4, 0, -4, 0)
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, 
                         os.path.basename(path))
        painter.end()
        
        drag.setPixmap(pix)
        drag.setHotSpot(QPoint(10, 10))
        drag.exec(Qt.DropAction.CopyAction)


class RecommendedFilesList(QListWidget):
    """Draggable list for recommended form files — drag items into Policy Subfolders."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole) or ""
        if not path or not os.path.isfile(path):
            return

        mime = QMimeData()
        mime.setData(_MIME_TOOL_FILE, path.encode())
        drag = QDrag(self)
        drag.setMimeData(mime)

        # Themed drag pixmap
        pix = QPixmap(220, 20)
        pix.fill(QColor(CRIMSON_SUBTLE))

        painter = QPainter(pix)
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.setPen(QColor(CRIMSON_PRIMARY))
        painter.drawRect(0, 0, 219, 19)
        painter.setPen(QColor(CRIMSON_DARK))
        rect = pix.rect().adjusted(4, 0, -4, 0)
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         os.path.basename(path))
        painter.end()

        drag.setPixmap(pix)
        drag.setHotSpot(QPoint(10, 10))
        drag.exec(Qt.DropAction.CopyAction)


class OutputPanel(QWidget):
    """
    Output/File Management Panel.
    
    Layout:
      Left column:
        - Policy Subfolders (compact, drop target)
        - Recommended Files (state-specific forms from DB)
      Right column:
        - Resources (general ABR folder browser)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: Optional[ABRPolicyData] = None
        self._result: Optional[ABRQuoteResult] = None
        self._assessment: Optional[MedicalAssessment] = None
        self._derived_values: dict = {}
        self._mort_detail: list[dict] = []
        self._apv_detail: list[dict] = []
        self._apv_summary: dict = {}
        self._accel_inputs_fn = None  # callback returning (accel_amount, min_face)
        self._after_partial_deduction_fn = None
        self._policy_folder_path = ""
        self._tools_root_path = self._get_tools_root_path()
        self._sync_warned = False
        
        self._setup_ui()
        
        # Initialize
        self._update_ui_state()
        self._check_onedrive_sync()

    def _get_onedrive_dir(self) -> str:
        return onedrive_directory()

    def _get_tools_root_path(self) -> str:
        return abr_support_directory()

    def _is_onedrive_synced(self) -> bool:
        """Check whether the OneDrive folder is actively synced (not just a local directory)."""
        onedrive_dir = self._get_onedrive_dir()
        ini_path = os.path.join(onedrive_dir, "desktop.ini")
        if os.path.isfile(ini_path):
            try:
                with open(ini_path, "r", encoding="utf-8", errors="ignore") as f:
                    return "OneDrive" in f.read()
            except (PermissionError, OSError):
                pass
        return False

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        # ── Top info bar ──────────────────────────────────────────────────
        info_frame = QGroupBox("Policy Support")
        info_frame.setStyleSheet(POLICY_INFO_FRAME_STYLE_ABR)
        ig = QGridLayout(info_frame)
        ig.setContentsMargins(12, 24, 12, 8)
        ig.setHorizontalSpacing(10)
        ig.setVerticalSpacing(4)

        lbl_s = f"font-size: 11px; font-weight: bold; color: {CRIMSON_DARK}; background: transparent; border: none;"
        val_s = f"font-size: 11px; color: {GRAY_DARK}; background: transparent; border: none;"
        path_s = f"""
            font-size: 11px; color: {CRIMSON_DARK};
            background: #F9E0E3; border: 1px solid {CRIMSON_PRIMARY};
            border-radius: 3px; padding: 2px 6px;
        """

        # Row 0: Policy Folder label
        ig.addWidget(self._mk_lbl("Policy Folder:", lbl_s), 0, 0)
        self._policy_folder_label = QLabel("No policy loaded")
        self._policy_folder_label.setStyleSheet(val_s)
        ig.addWidget(self._policy_folder_label, 0, 1, 1, 2)  # span 2 cols

        # Row 1: Library Path — full width (no label)
        self._library_path_label = DoubleClickablePathLabel("")
        self._library_path_label.setStyleSheet(path_s)
        ig.addWidget(self._library_path_label, 1, 0, 1, 3)  # span all 3 cols

        # Row 2: Create Folder button — left justified
        self._create_folder_btn = QPushButton("📁 Create")
        self._create_folder_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {SLATE_TEXT}, stop:1 {SLATE_PRIMARY});
                color: {WHITE};
                border: 1px solid {SLATE_DARK};
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {SLATE_PRIMARY}, stop:1 {SLATE_DARK});
                color: {WHITE};
            }}
        """)
        self._create_folder_btn.clicked.connect(self._on_create_policy_folder)
        self._create_folder_btn.setVisible(False)
        ig.addWidget(self._create_folder_btn, 2, 0, 1, 1)  # left-justified

        # Hidden status label (used internally for copy feedback)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"font-size: 10px; color: {GRAY_DARK}; background: transparent; border: none;")
        self._status_label.setVisible(False)

        ig.setColumnStretch(1, 1)
        layout.addWidget(info_frame)

        # ── Two-column Explorer ───────────────────────────────────────────
        cols = QWidget()
        cl = QHBoxLayout(cols)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(10)

        # ── Left column: Policy Subfolders + Recommended Files ──────────
        left_col = QWidget()
        left_layout = QVBoxLayout(left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # 1. Policy Subfolders (Drop Target) — compact
        self._subfolder_explorer = MiniExplorer(
            title="Policy Subfolders",
            list_widget_class=CrimsonDropTargetList,
            root_path="", # Will be set when policy loads
            support_files=True,
        )
        self._apply_abr_style(self._subfolder_explorer)

        # Print Detail button — small green button below subfolder group
        self._print_detail_btn = QPushButton("📋 Print Detail")
        self._print_detail_btn.setFixedHeight(22)
        self._print_detail_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4CAF50, stop:1 #388E3C);
                color: {WHITE};
                border: 1px solid #2E7D32;
                border-radius: 3px;
                padding: 1px 10px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #66BB6A, stop:1 #43A047);
            }}
            QPushButton:disabled {{
                background: #C8E6C9;
                color: #A5D6A7;
                border-color: #C8E6C9;
            }}
        """)
        self._print_detail_btn.setEnabled(False)
        self._print_detail_btn.clicked.connect(self._on_print_detail)
        self._subfolder_explorer.list_widget.file_dropped.connect(self._on_file_dropped)
        
        left_layout.addWidget(self._subfolder_explorer, 3)  # stretch=3 (bigger)

        # Place button in a right-aligned row below the subfolder explorer
        detail_row = QHBoxLayout()
        detail_row.addStretch()
        detail_row.addWidget(self._print_detail_btn)
        left_layout.addLayout(detail_row)

        self._copy_up_btn = QPushButton("Copy ↑")
        self._copy_up_btn.setStyleSheet(f"""
            QPushButton {{
                background: {CRIMSON_SUBTLE};
                color: {CRIMSON_DARK};
                border: 1px solid {CRIMSON_PRIMARY};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {CRIMSON_PRIMARY};
                color: {WHITE};
            }}
        """)
        self._copy_up_btn.clicked.connect(self._on_copy_recommended)
        
        btn_layout_up = QHBoxLayout()
        btn_layout_up.addStretch(1)
        btn_layout_up.addWidget(self._copy_up_btn)
        btn_layout_up.addStretch(1)
        left_layout.addLayout(btn_layout_up)

        # 2. Recommended Forms — state-based forms from DB
        self._recommended_group = QGroupBox("Recommended Forms")
        self._recommended_group.setStyleSheet(ABR_EXPLORER_BOX_STYLE)
        rec_layout = QVBoxLayout(self._recommended_group)
        rec_layout.setContentsMargins(4, 20, 4, 4)
        rec_layout.setSpacing(2)

        # State label at top
        self._rec_state_label = QLabel("No state loaded")
        self._rec_state_label.setStyleSheet(f"""
            font-size: 10px; color: {CRIMSON_DARK}; font-weight: bold;
            background: #F9E0E3; border: 1px solid {CRIMSON_PRIMARY};
            border-radius: 3px; padding: 2px 6px;
        """)
        rec_layout.addWidget(self._rec_state_label)

        # Draggable list of recommended files
        self._recommended_list = RecommendedFilesList()
        self._recommended_list.setStyleSheet(ABR_LIST_STYLE)
        self._recommended_list.setItemDelegate(TightItemDelegate(self._recommended_list))
        self._recommended_list.setUniformItemSizes(True)
        self._recommended_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        # Double-click to open the file
        self._recommended_list.itemDoubleClicked.connect(self._on_recommended_dblclick)
        rec_layout.addWidget(self._recommended_list, 1)

        # Hint label
        hint = QLabel("Drag files ↑ to Policy Subfolders")
        hint.setStyleSheet(f"font-size: 9px; color: {GRAY_MID}; font-style: italic; background: transparent; border: none;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rec_layout.addWidget(hint)

        left_layout.addWidget(self._recommended_group, 2)  # stretch=2

        cl.addWidget(left_col, 1)

        self._copy_left_btn = QPushButton("← Copy")
        self._copy_left_btn.setStyleSheet(f"""
            QPushButton {{
                background: {CRIMSON_SUBTLE};
                color: {CRIMSON_DARK};
                border: 1px solid {CRIMSON_PRIMARY};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {CRIMSON_PRIMARY};
                color: {WHITE};
            }}
        """)
        self._copy_left_btn.clicked.connect(self._on_copy_resource)
        
        btn_layout_left = QVBoxLayout()
        btn_layout_left.addStretch(1)
        btn_layout_left.addWidget(self._copy_left_btn)
        btn_layout_left.addStretch(1)
        
        cl.addLayout(btn_layout_left)

        # ── Right column: Resources (formerly Available Tools) ─────────
        self._tools_explorer = MiniExplorer(
            title="Resources",
            list_widget_class=CrimsonDraggableToolsList,
            root_path=self._tools_root_path,
            support_files=True,
        )
        self._apply_abr_style(self._tools_explorer)
        if hasattr(self._tools_explorer, 'list_widget') and self._tools_explorer.list_widget:
            self._tools_explorer.list_widget.setSelectionMode(
                QAbstractItemView.SelectionMode.ExtendedSelection
            )
        
        cl.addWidget(self._tools_explorer, 1)

        layout.addWidget(cols, 1)
        self._support_access_note = QLabel(
            "Read-only support files — your role cannot create, copy, rename, delete or print files."
        )
        self._support_access_note.setWordWrap(True)
        self._support_access_note.setStyleSheet(
            f"color: {GRAY_MID}; font-size: 10px; font-style: italic;"
        )
        layout.addWidget(self._support_access_note)
        self._refresh_support_access()

    def _refresh_support_access(self):
        writable = can_write_support_files()
        self._support_access_note.setVisible(not writable)
        for button in (self._create_folder_btn, self._copy_up_btn, self._copy_left_btn):
            button.setEnabled(writable)
            button.setToolTip("" if writable else "Your role cannot modify policy support files.")
        self._print_detail_btn.setEnabled(bool(writable and self._policy and self._result))
        self._print_detail_btn.setToolTip(
            "" if writable else "Your role cannot save policy support detail workbooks."
        )
        self._subfolder_explorer.list_widget.setAcceptDrops(writable)

    def _apply_abr_style(self, explorer: MiniExplorer):
        """Inject ABR stylesheets into MiniExplorer components."""
        # Find the group box (container)
        gb = explorer.findChild(QGroupBox)
        if gb:
            gb.setStyleSheet(ABR_EXPLORER_BOX_STYLE)

        # Find nav buttons (using private members since we know the class structure)
        if hasattr(explorer, '_home_btn'):
            explorer._home_btn.setStyleSheet(ABR_NAV_BTN_STYLE)
        if hasattr(explorer, '_up_btn'):
            explorer._up_btn.setStyleSheet(ABR_NAV_BTN_STYLE)
        
        # Path label
        if hasattr(explorer, '_path_label'):
            explorer._path_label.setStyleSheet(ABR_PATH_BAR_STYLE)
            
        # List widget
        if hasattr(explorer, 'list_widget'):
            explorer.list_widget.setStyleSheet(ABR_LIST_STYLE)

    @staticmethod
    def _mk_lbl(text: str, style: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet(style)
        return l

    # ── Policy Loading ──────────────────────────────────────────────────

    def set_policy(self, policy: Optional[ABRPolicyData]):
        self._policy = policy
        self._result = None
        self._assessment = None
        self._derived_values = {}
        self._mort_detail = []
        self._apv_detail = []
        self._apv_summary = {}
        self._print_detail_btn.setEnabled(False)
        self._update_ui_state()

    def set_result(self, result: ABRQuoteResult):
        self._result = result
        self._refresh_support_access()

    def set_assessment(self, assessment: MedicalAssessment):
        self._assessment = assessment

    def set_calc_data(self, mort_detail: list, apv_detail: list, apv_summary: dict):
        self._mort_detail = mort_detail
        self._apv_detail = apv_detail
        self._apv_summary = apv_summary

    def set_derived_values(self, derived_values: dict):
        self._derived_values = derived_values or {}

    def set_accel_inputs(self, accel_amount: float, min_face_amount: float):
        self._accel_inputs_fn = lambda: (accel_amount, min_face_amount)

    def set_accel_inputs_fn(self, fn):
        """Set a callback that returns (accel_amount, min_face_amount) at print time."""
        self._accel_inputs_fn = fn

    def set_after_partial_deduction_fn(self, fn):
        """Set a callback returning the current UL deduction at print time."""
        self._after_partial_deduction_fn = fn

    def _get_after_partial_deduction(self) -> str:
        """Return the current user-entered UL deduction, if any."""
        if not self._after_partial_deduction_fn:
            return ""
        return str(self._after_partial_deduction_fn() or "").strip()

    def _get_accel_inputs(self) -> tuple[float, float]:
        """Return current (accel_amount, min_face_amount) from callback or defaults."""
        if self._accel_inputs_fn:
            try:
                return self._accel_inputs_fn()
            except Exception:
                pass
        p = self._policy
        return (p.face_amount if p else 0.0, p.min_face_amount if p else 0.0)

    def _update_ui_state(self):
        self._refresh_support_access()
        if not self._policy:
            self._policy_folder_label.setText("No policy loaded")
            self._library_path_label.setText("")
            self._status_label.setText("")
            self._create_folder_btn.setVisible(False)
            self._subfolder_explorer.set_root("")
            self._clear_recommended()
            return

        # Path: ...\Policies\PolicyNumber
        pn = self._policy.policy_number
        policies_dir = os.path.join(self._tools_root_path, "Policies")
        self._policy_folder_path = os.path.join(policies_dir, pn)
        
        if os.path.exists(self._policy_folder_path):
            self._policy_folder_label.setText(pn)
            self._policy_folder_label.setStyleSheet(
                f"font-size: 11px; color: {CRIMSON_DARK}; font-weight: bold; background: transparent; border: none;"
            )
            # Show full path (folder exists, double-click works)
            self._library_path_label.setText(self._policy_folder_path)
            self._create_folder_btn.setVisible(False)
            self._subfolder_explorer.set_root(self._policy_folder_path)
        else:
            self._policy_folder_label.setText(f"{pn} — No Folder Found")
            self._policy_folder_label.setStyleSheet(
                f"font-size: 11px; color: #C00000; font-weight: bold; background: transparent; border: none;"
            )
            # Show parent Policies dir (which exists) so double-click opens something useful
            self._library_path_label.setText(policies_dir if os.path.isdir(policies_dir) else self._tools_root_path)
            self._create_folder_btn.setVisible(True)
            self._subfolder_explorer.set_root("")

        # Load recommended files based on state
        self._load_recommended_files()

    # ── Recommended Files ───────────────────────────────────────────────

    def _clear_recommended(self):
        """Clear the recommended files list."""
        self._recommended_list.clear()
        self._rec_state_label.setText("No state loaded")

    def _load_recommended_files(self):
        """Query the state_variations table for the policy's issue_state and populate the list."""
        self._recommended_list.clear()

        if not self._policy or not self._policy.issue_state:
            self._rec_state_label.setText("No state loaded")
            return

        state_abbr = self._policy.issue_state.upper().strip()
        self._rec_state_label.setText(f"State: {state_abbr}")

        # Query the ABR database for form files associated with this state
        try:
            from ..models.abr_database import get_abr_database
            db = get_abr_database()
            conn = db.connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT state_name, election_form, "
                "       disclosure_form_critical, disclosure_form_chronic,"
                "       disclosure_form_terminal "
                "FROM [SV_ABR_STATE_VARIATIONS] "
                "WHERE state_abbr = ?",
                (state_abbr,)
            )
            row = cursor.fetchone()
            cursor.close()

            if not row:
                self._rec_state_label.setText(f"State: {state_abbr} (not in DB)")
                item = QListWidgetItem("  No forms found for this state")
                item.setForeground(QColor(GRAY_MID))
                self._recommended_list.addItem(item)
                return

            state_name = row[0] or state_abbr
            self._rec_state_label.setText(f"State: {state_abbr} — {state_name}")

            # Collect form file names (skip empty/None)
            form_fields = [
                ("Election Form", row[1]),
                ("Disclosure (Critical)", row[2]),
                ("Disclosure (Chronic)", row[3]),
                ("Disclosure (Terminal)", row[4]),
            ]

            # Known directories where form files may live
            forms_base = os.path.join(self._tools_root_path, "Forms")
            search_dirs = [
                os.path.join(forms_base, "ABR Election Forms"),
                os.path.join(forms_base, "ABR Disclosure Forms", "ABR14"),
                os.path.join(forms_base, "ABR Disclosure Forms", "ABR11"),
                os.path.join(forms_base, "ABR Disclosure Forms"),
                forms_base,
            ]

            seen_files = set()  # avoid duplicates
            for label, filename in form_fields:
                if not filename or not filename.strip():
                    continue
                filename = filename.strip()
                if filename in seen_files:
                    continue
                seen_files.add(filename)

                # Try to find the actual file on disk
                full_path = self._find_form_file(filename, search_dirs)

                ext = os.path.splitext(filename)[1].lower()
                icon = icon_for_ext(ext)

                if full_path:
                    item = QListWidgetItem(f"{icon}  {filename}")
                    item.setData(Qt.ItemDataRole.UserRole, full_path)
                    item.setToolTip(f"{label}\n{full_path}")
                else:
                    item = QListWidgetItem(f"⚠️  {filename}")
                    item.setForeground(QColor(GRAY_MID))
                    item.setToolTip(f"{label}\nFile not found on disk")
                
                self._recommended_list.addItem(item)

            if self._recommended_list.count() == 0:
                item = QListWidgetItem("  No forms configured for this state")
                item.setForeground(QColor(GRAY_MID))
                self._recommended_list.addItem(item)

        except Exception as e:
            logger.error(f"Error loading recommended files: {e}", exc_info=True)
            self._rec_state_label.setText(f"State: {state_abbr} (error)")
            item = QListWidgetItem(f"  Error: {e}")
            item.setForeground(QColor("#C00000"))
            self._recommended_list.addItem(item)

    def _find_form_file(self, filename: str, search_dirs: List[str]) -> Optional[str]:
        """Search for a form file in the known directories. Returns full path or None."""
        for d in search_dirs:
            if not os.path.isdir(d):
                continue
            candidate = os.path.join(d, filename)
            if os.path.isfile(candidate):
                return candidate
        return None

    def _on_recommended_dblclick(self, item: QListWidgetItem):
        """Open the recommended file when double-clicked."""
        path = item.data(Qt.ItemDataRole.UserRole) or ""
        if path and os.path.isfile(path):
            os.startfile(path)

    # ── Actions ─────────────────────────────────────────────────────────

    def _check_onedrive_sync(self):
        """Warn once if the OneDrive folder does not appear to be synced."""
        if self._sync_warned:
            return
        onedrive_dir = self._get_onedrive_dir()
        if not os.path.isdir(onedrive_dir):
            self._sync_warned = True
            QMessageBox.warning(
                self, "OneDrive Not Found",
                f"The OneDrive folder was not found:\n\n"
                f"{onedrive_dir}\n\n"
                "Please make sure OneDrive is installed and you are signed in "
                "with your corporate account."
            )
        elif not self._is_onedrive_synced():
            self._sync_warned = True
            QMessageBox.warning(
                self, "OneDrive Sync Issue",
                f"The OneDrive folder exists but does not appear to be actively "
                f"synced to SharePoint:\n\n"
                f"{onedrive_dir}\n\n"
                "Files saved here may only exist locally and will NOT be visible "
                "to others on SharePoint.\n\n"
                "To fix this:\n"
                "1. Open the SharePoint site in your browser\n"
                "2. Navigate to the document library\n"
                "3. Click the 'Sync' button in the toolbar"
            )

    def _on_create_policy_folder(self):
        if not self._policy_folder_path:
            return
        if not self._is_onedrive_synced():
            self._check_onedrive_sync()
            return
        try:
            guard_support_files_writable("create policy support folders")
            os.makedirs(self._policy_folder_path, exist_ok=True)
            self._update_ui_state()
            QMessageBox.information(self, "Success", "Policy folder created.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to create policy folder:\n{e}")

    def _do_copy_files(self, source_paths: List[str]):
        if not source_paths:
            return
            
        dest_dir = self._subfolder_explorer.current_path()
        if not dest_dir or not os.path.isdir(dest_dir):
            if self._policy_folder_path and os.path.isdir(self._policy_folder_path):
                 dest_dir = self._policy_folder_path
            else:
                QMessageBox.information(
                    self, "No Destination",
                    "Please create/open the policy folder first."
                )
                return

        copied_count = 0
        errors = []
        for source_path in source_paths:
            if not source_path or not os.path.isfile(source_path):
                continue
                
            filename = workbook_filename(os.path.basename(source_path))
            if self._policy:
                dest_filename = f"{self._policy.policy_number} - {filename}"
            else:
                dest_filename = filename

            dest_path = os.path.join(dest_dir, dest_filename)
            if os.path.exists(dest_path):
                errors.append(f"'{dest_filename}' already exists.")
                continue

            try:
                copy_as_workbook(source_path, dest_path, support_files=True)
                copied_count += 1
            except Exception as e:
                errors.append(f"Failed to copy '{filename}': {e}")
                
        if copied_count > 0:
            self._status_label.setText(f"✓ Copied {copied_count} file(s)")
            self._subfolder_explorer.refresh()
            
        if errors:
            QMessageBox.warning(self, "Copy Issues", "\n".join(errors))

    def _on_copy_recommended(self):
        items = self._recommended_list.selectedItems()
        paths = [i.data(Qt.ItemDataRole.UserRole) for i in items if i.data(Qt.ItemDataRole.UserRole)]
        self._do_copy_files(paths)

    def _on_copy_resource(self):
        if not hasattr(self._tools_explorer, 'list_widget') or not self._tools_explorer.list_widget:
            return
        items = self._tools_explorer.list_widget.selectedItems()
        paths = [i.data(Qt.ItemDataRole.UserRole) for i in items if i.data(Qt.ItemDataRole.UserRole)]
        self._do_copy_files(paths)

    def _on_file_dropped(self, source_path: str):
        """Handle file copy from Tools/Recommended to Policy folder."""
        self._do_copy_files([source_path])

    # ── Print Detail ────────────────────────────────────────────────────

    def _on_print_detail(self):
        """Generate a detail workbook and save it to the policy folder."""
        if not self._policy or not self._result:
            return

        from datetime import datetime

        now = datetime.now()
        timestamp = now.strftime("%m-%d-%Y %H%M%S")
        pn = self._policy.policy_number
        filename = f"{pn} - details - {timestamp}.xlsx"

        # Determine destination folder
        dest_dir = self._subfolder_explorer.current_path()
        if not dest_dir or not os.path.isdir(dest_dir):
            if self._policy_folder_path and os.path.isdir(self._policy_folder_path):
                dest_dir = self._policy_folder_path
            else:
                QMessageBox.information(
                    self, "No Destination",
                    "Please create the policy folder first.",
                )
                return

        filepath = os.path.join(dest_dir, filename)

        try:
            self._write_detail_workbook(filepath)
            self._subfolder_explorer.refresh()
            QMessageBox.information(
                self, "Print Detail",
                f"Detail workbook saved:\n{filename}",
            )
        except Exception as e:
            logger.error(f"Print Detail error: {e}", exc_info=True)
            QMessageBox.warning(
                self, "Print Detail Error",
                f"Could not create workbook:\n{e}",
            )

    def _write_detail_workbook(self, filepath: str):
        """Write the ABR detail workbook through the shared workbook spec."""
        from ..core.output_spec import build_detail_workbook_spec, write_openpyxl

        accel_amount, min_face = self._get_accel_inputs()
        spec = build_detail_workbook_spec(
            self._policy,
            self._result,
            self._assessment,
            self._mort_detail,
            self._apv_detail,
            self._apv_summary,
            derived_values=self._derived_values,
            accel_amount=accel_amount,
            min_face_amount=min_face,
            after_partial_override=self._get_after_partial_deduction(),
            apv_sheet_name="APV - Present Value",
        )
        guard_support_files_writable("save policy support detail workbooks")
        write_openpyxl(spec, filepath)
