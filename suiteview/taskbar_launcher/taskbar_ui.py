"""SuiteViewTaskbar UI construction helpers."""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QPainter,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from suiteview import __version__ as APP_VERSION
from suiteview.administrator.launcher import AdministratorMenuAccess
from suiteview.taskbar_launcher.albert_launcher import AlbertButton
from suiteview.ui.widgets.bookmark_widgets import (
    set_footer_status_callback,
)
from suiteview.ui.widgets.uppercase_input import force_uppercase
from suiteview.taskbar_launcher.collaborators import TaskbarCollaborator

logger = logging.getLogger(__name__)


class TaskbarChrome(TaskbarCollaborator):
    """Builds taskbar widgets and wires user-facing controls."""

    def __init__(self, window, state, callbacks):
        super().__init__(window, state, callbacks=callbacks)
        self._permission_actions = []

    def init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self.window)
        layout.setContentsMargins(2, 2, 2, 2)  # Small margin for resize handles
        layout.setSpacing(0)

        self._apply_global_scrollbar_style()
        header_layout = self._build_header_bar()
        self._build_quick_capture_and_policy_controls(header_layout)
        self._build_app_buttons(header_layout)
        self._build_tools_menu(header_layout)
        self._build_window_controls(header_layout)
        layout.addWidget(self.header_bar)
        self._build_tab_widget(layout)
        self._build_footer_bar(layout)
        self._document_pending_keyboard_shortcuts()

    def _apply_global_scrollbar_style(self):
        # ====== GLOBAL SCROLLBAR STYLING (light blue for contrast) ======
        self.window.setStyleSheet("""
            QScrollBar:vertical {
                background: #E8F0F8;
                width: 12px;
                margin: 0;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #A8C8E8;
                min-height: 20px;
                border-radius: 5px;
                margin: 1px;
            }
            QScrollBar::handle:vertical:hover {
                background: #88B0D8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                background: #E8F0F8;
                height: 12px;
                margin: 0;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal {
                background: #A8C8E8;
                min-width: 20px;
                border-radius: 5px;
                margin: 1px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #88B0D8;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0;
                background: none;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)

    def _build_header_bar(self):
        # ====== HEADER BAR (Custom Title Bar) ======
        self.header_bar = QFrame()
        self.header_bar.setFixedHeight(38)
        self.header_bar.setMouseTracking(True)
        self.header_bar.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:0.5 #0D3A7A, stop:1 #082B5C);
                border: none;
            }
        """)
        self.header_bar.setCursor(Qt.CursorShape.ArrowCursor)
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(12, 4, 8, 4)
        header_layout.setSpacing(8)
        
        # App title (acts as drag handle) - larger and italic
        self.title_label = QLabel(f"SuiteView ({APP_VERSION})")
        self.title_label.setStyleSheet("""
            QLabel {
                color: #D4A017;
                font-size: 18px;
                font-weight: bold;
                font-style: italic;
                background: transparent;
                padding-right: 4px;
            }
        """)
        self.title_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title_label.mouseDoubleClickEvent = lambda event: self.callbacks._toggle_compact_mode()
        header_layout.addWidget(self.title_label)
        return header_layout

    def _build_quick_capture_and_policy_controls(self, header_layout):
        # ====== QUICK SCREENSHOT BUTTON (yellow dot) ======
        self.quick_screenshot_btn = QPushButton()
        self.quick_screenshot_btn.setFixedSize(28, 28)
        self.quick_screenshot_btn.setToolTip("Take Screenshot (saves to Screenshots folder)")
        self.quick_screenshot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Create icon with yellow dot
        dot_pixmap = QPixmap(24, 24)
        dot_pixmap.fill(Qt.GlobalColor.transparent)
        dot_painter = QPainter(dot_pixmap)
        dot_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dot_painter.setBrush(QBrush(QColor("#FFD700")))  # Yellow/gold dot
        dot_painter.setPen(Qt.PenStyle.NoPen)
        dot_painter.drawEllipse(6, 6, 12, 12)  # Centered dot
        dot_painter.end()
        self.quick_screenshot_btn.setIcon(QIcon(dot_pixmap))
        self.quick_screenshot_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 2px solid #D4A017;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: rgba(212, 160, 23, 0.2);
                border-color: #FFD700;
            }
            QPushButton:pressed {
                background: rgba(212, 160, 23, 0.4);
            }
        """)
        self.quick_screenshot_btn.clicked.connect(lambda _checked=False: self.callbacks._take_quick_screenshot())
        header_layout.addWidget(self.quick_screenshot_btn)
        
        # ====== COMPACT MODE: Region combo + Policy input ======
        # Placed after screenshot button. Only visible when docked.
        self.compact_region_combo = QComboBox()
        self.compact_region_combo.addItems(["CKPR", "CKMO", "CKAS", "CKSR"])
        self.compact_region_combo.setFixedHeight(28)
        self.compact_region_combo.setToolTip("Region")
        self.compact_region_combo.setStyleSheet("""
            QComboBox {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:1 #0D3A7A);
                border: 2px solid #D4A017;
                border-radius: 4px;
                color: #FFD700;
                font-size: 13px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
                padding: 0px 6px;
            }
            QComboBox:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2A6FBF, stop:1 #1E5BA8);
                border-color: #FFD700;
            }
            QComboBox::drop-down {
                border: none;
                width: 0px;
            }
            QComboBox::down-arrow {
                image: none;
                width: 0px;
                height: 0px;
                border: none;
            }
            QComboBox QAbstractItemView {
                background: #0D3A7A;
                color: #FFD700;
                selection-background-color: #3A7DC8;
                selection-color: white;
                font-size: 13px;
                font-weight: bold;
                border: 1px solid #D4A017;
                outline: none;
            }
        """)
        self.compact_region_combo.hide()
        header_layout.addWidget(self.compact_region_combo)

        self.compact_policy_input = QLineEdit()
        self.compact_policy_input.setPlaceholderText("Policy #")
        self.compact_policy_input.setFixedWidth(100)
        self.compact_policy_input.setFixedHeight(28)
        self.compact_policy_input.setStyleSheet("""
            QLineEdit {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:1 #0D3A7A);
                border: 2px solid #D4A017;
                border-radius: 4px;
                color: #FFD700;
                font-size: 13px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
                padding: 0px 4px;
            }
            QLineEdit:focus {
                border-color: #FFD700;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2A6FBF, stop:1 #1E5BA8);
            }
            QLineEdit::placeholder {
                color: rgba(212, 160, 23, 0.5);
            }
        """)
        self.compact_policy_input.setToolTip("Policy Number")
        self.compact_policy_input.returnPressed.connect(self.callbacks._open_polview_with_policy)
        self.compact_policy_input.hide()
        force_uppercase(self.compact_policy_input)
        header_layout.addWidget(self.compact_policy_input)

    def _build_app_buttons(self, header_layout):
        self._build_primary_app_buttons(header_layout)
        self._build_utility_app_buttons(header_layout)

    def _build_primary_app_buttons(self, header_layout):
        # ====== POLVIEW BUTTON (green "P" with gold trim) ======
        self.polview_btn = QPushButton("P")
        self.polview_btn.setFixedSize(28, 28)
        self.polview_btn.setToolTip("Open PolView - Policy Viewer")
        self.polview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.polview_btn.setStyleSheet("""
            QPushButton {
                background: #2E7D32;
                border: 2px solid #D4A017;
                border-radius: 4px;
                color: #FFD700;
                font-size: 14px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: #388E3C;
                border-color: #FFD700;
            }
            QPushButton:pressed {
                background: #1B5E20;
            }
        """)
        self.polview_btn.clicked.connect(lambda _checked=False: self.callbacks._polview_btn_clicked())
        header_layout.addWidget(self.polview_btn)

        # ====== FILE NAV BUTTON (gold "F" with blue trim) ======
        self.filenav_btn = QPushButton("F")
        self.filenav_btn.setFixedSize(28, 28)
        self.filenav_btn.setToolTip("Open File Navigator")
        self.filenav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.filenav_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:1 #0D3A7A);
                border: 2px solid #D4A017;
                border-radius: 4px;
                color: #D4A017;
                font-size: 14px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2A6FBF, stop:1 #1E5BA8);
                border-color: #FFD700;
            }
            QPushButton:pressed {
                background: #082B5C;
                border-color: #FFD700;
            }
        """)
        self.filenav_btn.clicked.connect(lambda _checked=False: self.callbacks._open_file_nav())
        header_layout.addWidget(self.filenav_btn)

        # ====== ABR QUOTE BUTTON (crimson "A" with slate-blue trim) ======
        self.abrquote_btn = QPushButton("A")
        self.abrquote_btn.setFixedSize(28, 28)
        self.abrquote_btn.setToolTip("Open ABR Quote Tool")
        self.abrquote_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.abrquote_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8B1A2A, stop:1 #5C0A14);
                border: 2px solid #4A6FA5;
                border-radius: 4px;
                color: #B8D0F0;
                font-size: 14px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #A52535, stop:1 #8B1A2A);
                border-color: #7AA0D5;
                color: #D8E8FF;
            }
            QPushButton:pressed {
                background: #5C0A14;
                border-color: #2E4F85;
            }
        """)
        self.abrquote_btn.clicked.connect(lambda _checked=False: self.callbacks._abrquote_btn_clicked())
        header_layout.addWidget(self.abrquote_btn)

        # ====== RERUN BUTTON (gold "R" on purple) ======
        self.illustration_btn = QPushButton("R")
        self.illustration_btn.setFixedSize(28, 28)
        self.illustration_btn.setToolTip("Open RERUN")
        self.illustration_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.illustration_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5E35A5, stop:1 #2A1458);
                border: 2px solid #D4A017;
                border-radius: 4px;
                color: #FFD700;
                font-size: 14px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7E57C2, stop:1 #5E35A5);
                border-color: #FFD700;
            }
            QPushButton:pressed {
                background: #2A1458;
            }
        """)
        self.illustration_btn.clicked.connect(lambda _checked=False: self.callbacks._illustration_btn_clicked())
        header_layout.addWidget(self.illustration_btn)
        
        # ====== AUDIT BUTTON ("Q" — silver & blue) ======
        self.audit_btn = QPushButton("Q")
        self.audit_btn.setFixedSize(28, 28)
        self.audit_btn.setToolTip("Open Audit Tool")
        self.audit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.audit_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #D0D0D0, stop:1 #A0A0A0);
                border: 2px solid #1E5BA8;
                border-radius: 4px;
                color: #1E5BA8;
                font-size: 14px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #E0E0E0, stop:1 #B0B0B0);
                border-color: #2A6FBF;
            }
            QPushButton:pressed {
                background: #909090;
            }
        """)
        self.audit_btn.clicked.connect(lambda _checked=False: self.callbacks._open_audit())
        header_layout.addWidget(self.audit_btn)
        self.albert_btn = AlbertButton(self.window)
        header_layout.addWidget(self.albert_btn)
        

    def _build_utility_app_buttons(self, header_layout):
        # ====== WINDOW CAPTURE BUTTON (blue dot) - HIDDEN FOR NOW ======
        # Functionality preserved in _capture_active_window() for future use
        # self.window_capture_btn = QPushButton()
        # self.window_capture_btn.setFixedSize(28, 28)
        # self.window_capture_btn.setToolTip("Capture Active Window (saves to Screenshots folder)")
        # self.window_capture_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # # Create icon with blue dot
        # win_dot_pixmap = QPixmap(24, 24)
        # win_dot_pixmap.fill(Qt.GlobalColor.transparent)
        # win_dot_painter = QPainter(win_dot_pixmap)
        # win_dot_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # win_dot_painter.setBrush(QBrush(QColor("#4A90D9")))  # Blue dot
        # win_dot_painter.setPen(Qt.PenStyle.NoPen)
        # win_dot_painter.drawEllipse(6, 6, 12, 12)  # Centered dot
        # win_dot_painter.end()
        # self.window_capture_btn.setIcon(QIcon(win_dot_pixmap))
        # self.window_capture_btn.setStyleSheet("""
        #     QPushButton {
        #         background: transparent;
        #         border: 2px solid #4A90D9;
        #         border-radius: 4px;
        #     }
        #     QPushButton:hover {
        #         background: rgba(74, 144, 217, 0.2);
        #         border-color: #6AB0F9;
        #     }
        #     QPushButton:pressed {
        #         background: rgba(74, 144, 217, 0.4);
        #     }
        # """)
        # self.window_capture_btn.clicked.connect(self._capture_active_window)
        # header_layout.addWidget(self.window_capture_btn)
        # ====== SCRATCHPAD BUTTON (📝 parchment green) ======
        self.scratchpad_window_btn = QPushButton("📝")
        self.scratchpad_window_btn.setFixedSize(28, 28)
        self.scratchpad_window_btn.setToolTip("Open ScratchPad")
        self.scratchpad_window_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scratchpad_window_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2D6A3F, stop:1 #163820);
                border: 2px solid #C8A84B;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3D8A55, stop:1 #2D6A3F);
                border-color: #E0C070;
            }
            QPushButton:pressed {
                background: #163820;
                border-color: #C8A84B;
            }
        """)
        self.scratchpad_window_btn.clicked.connect(lambda _checked=False: self.callbacks._toggle_scratchpad_window())
        header_layout.addWidget(self.scratchpad_window_btn)

        # ====== FILE OPEN HISTORY BUTTON (teal "H" with gold trim) ======
        self.file_history_btn = QPushButton("H")
        self.file_history_btn.setFixedSize(28, 28)
        self.file_history_btn.setToolTip("File Open History")
        self.file_history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.file_history_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1A7A6A, stop:1 #0D4A3F);
                border: 2px solid #D4A017;
                border-radius: 4px;
                color: #FFD700;
                font-size: 14px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #20907E, stop:1 #1A7A6A);
                border-color: #FFD700;
            }
            QPushButton:pressed {
                background: #0D4A3F;
            }
        """)
        self.file_history_btn.clicked.connect(lambda _checked=False: self.callbacks._toggle_file_open_history())
        header_layout.addWidget(self.file_history_btn)

    def _build_tools_menu(self, header_layout):
        # Tools dropdown menu button - gold text only
        self.tools_menu_btn = QPushButton("Tools")
        self.tools_menu_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                padding: 4px 12px;
                color: #D4A017;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                color: #FFD700;
            }
            QPushButton::menu-indicator {
                image: none;
            }
        """)
        
        # Create Tools menu
        self.tools_menu = QMenu(self.window)
        self.tools_menu.setStyleSheet("""
            QMenu {
                background-color: #1E5BA8;
                border: 1px solid #D4A017;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                background-color: transparent;
                color: white;
                padding: 6px 20px;
                font-size: 11px;
            }
            QMenu::item:selected {
                background-color: #3A7DC8;
            }
        """)
        self._permission_actions.append((
            "SCREENSHOT", self.tools_menu.addAction("View Screenshots", self.callbacks._open_screenshot)))
        self.administrator_action = self.tools_menu.addAction(
            "Administrator", self.callbacks._open_administrator)
        self._administrator_menu_access = AdministratorMenuAccess(
            self.tools_menu, self.administrator_action)
        for code, title, callback in (
            ("MAINFRAMENAV", "Mainframe Navigator", self.callbacks._open_mainframe),
            ("RATEMANAGER", "Rate Manager", self.callbacks._open_rate_manager),
            ("ADMINISTRATOR", "DB2 Table Check", self.callbacks._open_db2_table_check),
            ("EMAILATTACHMENTS", "Email Attachments", self.callbacks._open_email_attachments),
        ):
            self._permission_actions.append((code, self.tools_menu.addAction(title, callback)))
        self.tools_menu.addAction("Refresh Permissions", self.callbacks._refresh_permissions)
        self.tools_menu.addSeparator()
        self._permission_actions.append((
            "FILENAV", self.tools_menu.addAction("📁 App Data Location", self.callbacks._open_app_data_location)))
        self.tools_menu_btn.setMenu(self.tools_menu)
        header_layout.addWidget(self.tools_menu_btn)

        # Spacer between tools and window controls — hidden in compact mode
        self.header_spacer = QWidget()
        self.header_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.header_spacer.setMinimumWidth(20)
        header_layout.addWidget(self.header_spacer)

    def _build_window_controls(self, header_layout):
        # ====== WINDOW CONTROL BUTTONS ======
        window_btn_style = """
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 0px;
                padding: 0px;
                min-width: 40px;
                max-width: 40px;
                min-height: 28px;
                max-height: 28px;
                font-size: 14px;
                font-weight: bold;
            }
        """
        
        # Minimize button - gold text
        self.minimize_btn = QPushButton("–")
        self.minimize_btn.setStyleSheet(window_btn_style + """
            QPushButton {
                color: #D4A017;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
                color: #FFD700;
            }
        """)
        self.minimize_btn.setToolTip("Minimize")
        self.minimize_btn.clicked.connect(self.callbacks.showMinimized)
        header_layout.addWidget(self.minimize_btn)
        
        # Maximize/Restore button - gold text
        self.maximize_btn = QPushButton("□")
        self.maximize_btn.setStyleSheet(window_btn_style + """
            QPushButton {
                color: #D4A017;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
                color: #FFD700;
            }
        """)
        self.maximize_btn.setToolTip("Maximize")
        self.maximize_btn.clicked.connect(lambda _checked=False: self.callbacks._toggle_maximize())
        header_layout.addWidget(self.maximize_btn)
        
        # Close button - gold text
        self.close_btn = QPushButton("✕")
        self.close_btn.setStyleSheet(window_btn_style + """
            QPushButton {
                color: #D4A017;
            }
            QPushButton:hover {
                background-color: #E81123;
                color: #FFD700;
            }
        """)
        self.close_btn.setToolTip("Close to tray")
        self.close_btn.clicked.connect(lambda _checked=False: self.callbacks._hide_to_tray())
        header_layout.addWidget(self.close_btn)

    def _build_tab_widget(self, layout):
        # ====== TAB WIDGET ======
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        # Allow tab widget to shrink to 0 so window can collapse to just header bar
        self.tab_widget.setMinimumSize(0, 0)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background: #CCE5F8;
            }
            QTabBar {
                background: #CCE5F8;
            }
            QTabBar::tab {
                padding: 6px 14px;
                margin-right: 2px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4A7DC4, stop:1 #2A5AA4);
                color: white;
                font-weight: 600;
                font-size: 11px;
                border: 1px solid #1A4A94;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5A9DE8, stop:1 #3A7DC8);
                border-bottom: 3px solid #D4A017;
                color: white;
            }
            QTabBar::tab:!selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3A6AB4, stop:1 #1A4A94);
                color: #C8DCF8;
            }
            QTabBar::tab:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5A8DD4, stop:1 #3A6AB4);
            }
        """)
        self.tab_widget.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_widget.tabBar().customContextMenuRequested.connect(self.callbacks.show_tab_bar_context_menu)
        
        # Tab bar controls
        self.tab_widget.tabCloseRequested.connect(self.callbacks.close_tab)
        
        layout.addWidget(self.tab_widget)

    def _build_footer_bar(self, layout):
        # ====== FOOTER BAR (PolView style) ======
        self.footer_bar = QFrame()
        self.footer_bar.setMaximumHeight(24)
        self.footer_bar.setMinimumHeight(0)  # Allow footer to collapse
        self.footer_bar.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:0.5 #0D3A7A, stop:1 #082B5C);
                border: none;
                border-top: 1px solid #D4A017;
            }
        """)
        footer_layout = QHBoxLayout(self.footer_bar)
        footer_layout.setContentsMargins(12, 2, 12, 2)
        footer_layout.setSpacing(8)
        
        self.footer_status = QLabel("Ready")
        self.footer_status.setStyleSheet("""
            QLabel {
                color: #D4A017;
                font-size: 15px;
                background: transparent;
            }
        """)
        footer_layout.addWidget(self.footer_status)
        
        # Set up callback for bookmark hover to update footer status
        set_footer_status_callback(lambda path: self.footer_status.setText(path if path else "Ready"))
        
        footer_layout.addStretch()
        
        self.footer_size = QLabel("")
        self.footer_size.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 10px;
                background: transparent;
            }
        """)
        footer_layout.addWidget(self.footer_size)
        
        layout.addWidget(self.footer_bar)

    def _document_pending_keyboard_shortcuts(self):
        """Placeholder for the existing keyboard shortcut TODOs."""
        # Ctrl+T: New tab
        # Ctrl+W: Close tab
        # Ctrl+Tab: Next tab
        # Ctrl+Shift+Tab: Previous tab
