"""
SuiteView - Screen Shot Manager
Capture, organize, and export screenshots
"""

from suiteview.core.profile_paths import profile_path

import logging
import os
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QListWidget, QListWidgetItem, QMenu, 
                              QInputDialog, QMessageBox, QComboBox, QFrame,
                              QSizePolicy, QAbstractItemView, QSplitter)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon, QPainter, QColor, QBrush

from suiteview.ui.widgets.frameless_window import FramelessWindowBase

logger = logging.getLogger(__name__)


class ScreenshotThumbnail(QListWidgetItem):
    """Custom list item for screenshot thumbnail with metadata"""
    
    def __init__(self, screenshot_pixmap, screenshot_name, timestamp):
        super().__init__()
        self.screenshot_pixmap = screenshot_pixmap
        self.screenshot_name = screenshot_name
        self.timestamp = timestamp
        self.filepath = None  # Will be set after creation
        
        # Create thumbnail
        thumbnail = screenshot_pixmap.scaled(
            80, 60,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.setIcon(QIcon(thumbnail))
        self.setText(screenshot_name)
        self.setSizeHint(QSize(100, 80))


class ScreenshotListWidget(QListWidget):
    """Custom list widget with drag-and-drop reordering support"""
    
    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(80, 60))
        self.setSpacing(4)
        self.setMovement(QListWidget.Movement.Snap)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setWrapping(True)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setGridSize(QSize(100, 85))
        
        # Style - matching SuiteView theme
        self.setStyleSheet("""
            QListWidget {
                background-color: #E8EEF5;
                border: 2px solid #6B8DC9;
                border-radius: 4px;
                padding: 4px;
            }
            QListWidget::item {
                background-color: white;
                border: 2px solid #D4A017;
                border-radius: 4px;
                padding: 2px;
                margin: 2px;
                font-size: 8pt;
            }
            QListWidget::item:selected {
                background-color: #FFFDE7;
                border: 2px solid #1E5BA8;
            }
            QListWidget::item:hover {
                background-color: #F5F5F5;
                border-color: #FFD700;
            }
        """)


class ScreenShotManagerWindow(FramelessWindowBase):
    """Screen Shot Manager with capture, organize, and export functionality"""
    
    # Signal emitted when a new screenshot is added (for external listeners)
    screenshot_added = pyqtSignal(str)  # Emits filepath
    
    def __init__(self):
        from suiteview.core.access_control import guard_app_access
        guard_app_access("SCREENSHOT")

        self.screenshots = []  # List of (pixmap, name, timestamp, filepath) tuples
        self.screenshot_counter = 0
        self.current_viewer_pixmap = None
        self.screenshots_dir = profile_path('screenshots')
        self.archive_dir = profile_path('screenshots') / 'archive'
        self._viewing_archive = False  # Track if viewing archive

        super().__init__(
            title="SCREENSHOT MANAGER",
            default_size=(900, 500),
            min_size=(200, 50),
            header_colors=("#1E5BA8", "#0D3A7A", "#082B5C"),
            border_color="#D4A017",
            header_title_stretch=1,
        )
        self.setWindowTitle("SuiteView - Screenshot Manager")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_existing_screenshots()
        logger.info("Screenshot Manager initialized")
    
    def header_title_style(self):
        return """
            QLabel {
                color: #D4A017;
                font-size: 10pt;
                font-weight: 700;
                letter-spacing: 1px;
                background: transparent;
            }
        """

    def header_prefix_widgets(self):
        widgets = []

        # Grab button - styled like File Nav screenshot button with yellow dot
        self.grab_btn = QPushButton()
        self.grab_btn.setFixedSize(28, 28)
        self.grab_btn.setToolTip("Capture Screenshot")
        self.grab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Create icon with yellow dot
        dot_pixmap = QPixmap(24, 24)
        dot_pixmap.fill(Qt.GlobalColor.transparent)
        dot_painter = QPainter(dot_pixmap)
        dot_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dot_painter.setBrush(QBrush(QColor("#FFD700")))
        dot_painter.setPen(Qt.PenStyle.NoPen)
        dot_painter.drawEllipse(6, 6, 12, 12)
        dot_painter.end()
        self.grab_btn.setIcon(QIcon(dot_pixmap))
        self.grab_btn.setStyleSheet("""
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
        self.grab_btn.clicked.connect(self.grab_screenshot)
        widgets.append(self.grab_btn)

        # Window capture button - blue dot (captures active window only)
        self.window_capture_btn = QPushButton()
        self.window_capture_btn.setFixedSize(28, 28)
        self.window_capture_btn.setToolTip("Capture Active Window")
        self.window_capture_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Create icon with blue dot
        win_dot_pixmap = QPixmap(24, 24)
        win_dot_pixmap.fill(Qt.GlobalColor.transparent)
        win_dot_painter = QPainter(win_dot_pixmap)
        win_dot_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        win_dot_painter.setBrush(QBrush(QColor("#4A90D9")))
        win_dot_painter.setPen(Qt.PenStyle.NoPen)
        win_dot_painter.drawEllipse(6, 6, 12, 12)
        win_dot_painter.end()
        self.window_capture_btn.setIcon(QIcon(win_dot_pixmap))
        self.window_capture_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 2px solid #4A90D9;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: rgba(74, 144, 217, 0.2);
                border-color: #6AB0F9;
            }
            QPushButton:pressed {
                background: rgba(74, 144, 217, 0.4);
            }
        """)
        self.window_capture_btn.clicked.connect(self.capture_active_window)
        widgets.append(self.window_capture_btn)
        return widgets

    def header_widgets(self):
        widgets = []

        # Export controls
        self.export_type_combo = QComboBox()
        self.export_type_combo.addItems(["Word", "Outlook"])
        self.export_type_combo.setFixedSize(80, 26)
        self.export_type_combo.setStyleSheet("""
            QComboBox {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4A7DC4, stop:1 #2A5AA4);
                border: 1px solid #D4A017;
                border-radius: 3px;
                padding: 2px 6px;
                color: #D4A017;
                font-size: 9pt;
                font-weight: 600;
            }
            QComboBox:hover {
                border-color: #FFD700;
            }
            QComboBox::drop-down {
                border: none;
                width: 16px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #D4A017;
                margin-right: 4px;
            }
            QComboBox QAbstractItemView {
                background-color: #1E5BA8;
                color: #D4A017;
                selection-background-color: #3A7DC8;
                border: 1px solid #D4A017;
            }
        """)
        widgets.append(self.export_type_combo)

        # Export button
        self.export_btn = QPushButton("Export")
        self.export_btn.setFixedHeight(26)
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4A7DC4, stop:1 #2A5AA4);
                border: 1px solid #D4A017;
                border-radius: 3px;
                padding: 2px 12px;
                color: #D4A017;
                font-size: 9pt;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5A8DD4, stop:1 #3A6AB4);
                color: #FFD700;
            }
            QPushButton:pressed {
                background: #1E5BA8;
            }
            QPushButton:disabled {
                background: #555;
                color: #888;
                border-color: #666;
            }
        """)
        self.export_btn.clicked.connect(self.export_screenshots)
        self.export_btn.setEnabled(False)
        widgets.append(self.export_btn)

        # Archive toggle button
        self.archive_toggle_btn = QPushButton("📦 Archive")
        self.archive_toggle_btn.setFixedHeight(26)
        self.archive_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.archive_toggle_btn.setCheckable(True)
        self.archive_toggle_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4A7DC4, stop:1 #2A5AA4);
                border: 1px solid #D4A017;
                border-radius: 3px;
                padding: 2px 12px;
                color: #D4A017;
                font-size: 9pt;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5A8DD4, stop:1 #3A6AB4);
                color: #FFD700;
            }
            QPushButton:checked {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8B6914, stop:1 #6B4914);
                border-color: #FFD700;
                color: #FFD700;
            }
            QPushButton:checked:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #AB8924, stop:1 #8B6924);
            }
        """)
        self.archive_toggle_btn.setToolTip("Toggle view between Screenshots and Archive")
        self.archive_toggle_btn.clicked.connect(self._toggle_archive_view)
        widgets.append(self.archive_toggle_btn)
        return widgets

    def build_content(self):
        return self.init_ui()

    def init_ui(self):
        """Initialize the UI with SuiteView theme."""
        body = QWidget()
        main_layout = QVBoxLayout(body)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Content area - horizontal splitter
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.setHandleWidth(4)
        content_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #6090C0;
            }
            QSplitter::handle:hover {
                background-color: #D4A017;
            }
        """)
        
        # Left panel - Screenshots list
        left_panel = QFrame()
        left_panel.setStyleSheet("""
            QFrame {
                background-color: #E8EEF5;
                border: none;
            }
        """)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(2)
        
        # Screenshots header
        screenshots_header = QLabel("SCREENSHOTS")
        screenshots_header.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4A7DC4, stop:1 #2A5AA4);
                color: #D4A017;
                font-size: 9pt;
                font-weight: 700;
                padding: 4px 8px;
                border: 1px solid #1A4A94;
                border-radius: 3px;
            }
        """)
        screenshots_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        screenshots_header.setFixedHeight(24)
        left_layout.addWidget(screenshots_header)
        
        # Screenshot list
        self.screenshot_list = ScreenshotListWidget()
        self.screenshot_list.itemClicked.connect(self.display_screenshot)
        self.screenshot_list.itemSelectionChanged.connect(self.update_export_button)
        self.screenshot_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.screenshot_list.customContextMenuRequested.connect(self.show_context_menu)
        left_layout.addWidget(self.screenshot_list)
        
        # Left panel footer
        left_footer = QLabel("")
        left_footer.setStyleSheet("""
            QLabel {
                background-color: #E0E0E0;
                padding: 2px 8px;
                font-size: 8pt;
                color: #555555;
                border-top: 1px solid #A0B8D8;
            }
        """)
        left_footer.setFixedHeight(18)
        self.screenshots_footer = left_footer
        left_layout.addWidget(left_footer)
        
        content_splitter.addWidget(left_panel)
        
        # Right panel - Viewer
        right_panel = QFrame()
        right_panel.setStyleSheet("""
            QFrame {
                background-color: #E8EEF5;
                border: none;
            }
        """)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(2)
        
        # Viewer header
        viewer_header = QLabel("PREVIEW")
        viewer_header.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4A7DC4, stop:1 #2A5AA4);
                color: #D4A017;
                font-size: 9pt;
                font-weight: 700;
                padding: 4px 8px;
                border: 1px solid #1A4A94;
                border-radius: 3px;
            }
        """)
        viewer_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        viewer_header.setFixedHeight(24)
        right_layout.addWidget(viewer_header)
        
        # Viewer area
        self.viewer_area = QLabel()
        self.viewer_area.setStyleSheet("""
            QLabel {
                background-color: #FFFDE7;
                border: 2px solid #6B8DC9;
                border-radius: 4px;
            }
        """)
        self.viewer_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewer_area.setScaledContents(True)
        self.viewer_area.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.viewer_area.setMinimumSize(200, 200)
        right_layout.addWidget(self.viewer_area, 1)
        
        # Right panel footer
        right_footer = QLabel("Click a screenshot to preview")
        right_footer.setStyleSheet("""
            QLabel {
                background-color: #E0E0E0;
                padding: 2px 8px;
                font-size: 8pt;
                color: #555555;
                border-top: 1px solid #A0B8D8;
            }
        """)
        right_footer.setFixedHeight(18)
        self.viewer_footer = right_footer
        right_layout.addWidget(right_footer)
        
        content_splitter.addWidget(right_panel)
        
        # Set initial sizes for splitter (280px for left, rest for right)
        content_splitter.setSizes([280, 620])
        
        main_layout.addWidget(content_splitter, 1)
        
        # Window footer
        self.footer_bar = QFrame()
        self.footer_bar.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #082B5C, stop:1 #0D3A7A);
                border: none;
                border-top: 1px solid #D4A017;
            }
        """)
        self.footer_bar.setFixedHeight(20)
        
        footer_layout = QHBoxLayout(self.footer_bar)
        footer_layout.setContentsMargins(10, 2, 10, 2)
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #A0C4F0;
                font-size: 8pt;
                background: transparent;
            }
        """)
        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch()
        
        # Resize grip indicator
        resize_label = QLabel("⟋")
        resize_label.setStyleSheet("""
            QLabel {
                color: #D4A017;
                font-size: 10pt;
                background: transparent;
            }
        """)
        footer_layout.addWidget(resize_label)
        
        main_layout.addWidget(self.footer_bar)
        return body
    
    def _load_existing_screenshots(self):
        """Load existing screenshots from the screenshots folder"""
        try:
            # Clear current list
            self.screenshot_list.clear()
            self.screenshots.clear()
            self.viewer_area.clear()
            self.current_viewer_pixmap = None
            
            if not self.screenshots_dir.exists():
                self.screenshots_dir.mkdir(parents=True, exist_ok=True)
                self._update_footer()
                return
            
            # Get all PNG files sorted by modification time (newest first)
            # Exclude the archive folder
            png_files = sorted(
                [f for f in self.screenshots_dir.glob("*.png") if f.parent == self.screenshots_dir],
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            
            for filepath in png_files:
                try:
                    # Load the image
                    pixmap = QPixmap(str(filepath))
                    if pixmap.isNull():
                        continue
                    
                    # Get modification time
                    mtime = filepath.stat().st_mtime
                    timestamp = datetime.fromtimestamp(mtime)
                    
                    # Use filename (without extension) as the name
                    screenshot_name = filepath.stem
                    
                    # Add to list widget
                    item = ScreenshotThumbnail(pixmap, screenshot_name, timestamp)
                    item.filepath = filepath  # Store filepath for deletion
                    self.screenshot_list.addItem(item)
                    
                    # Store the data (include filepath)
                    self.screenshots.append((pixmap, screenshot_name, timestamp, filepath))
                    
                    # Update counter based on loaded screenshots
                    self.screenshot_counter += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to load screenshot {filepath}: {e}")
            
            # Enable export button if we have screenshots
            if self.screenshots:
                self.export_btn.setEnabled(True)
                logger.info(f"Loaded {len(self.screenshots)} existing screenshots")
            
            # Update footer
            self._update_footer()
                
        except Exception as e:
            logger.error(f"Failed to load existing screenshots: {e}")
    
    def _update_footer(self):
        """Update the screenshots footer with count"""
        count = len(self.screenshots)
        if hasattr(self, 'screenshots_footer'):
            if self._viewing_archive:
                self.screenshots_footer.setText(f"{count} archived screenshot(s)")
            else:
                self.screenshots_footer.setText(f"{count} screenshot(s)")
    
    def add_screenshot_from_file(self, filepath):
        """Add a screenshot from an external file (called by File Navigator)"""
        try:
            filepath = Path(filepath)
            if not filepath.exists():
                logger.warning(f"Screenshot file not found: {filepath}")
                return False
            
            # Check if already loaded
            for data in self.screenshots:
                if len(data) >= 4 and data[3] == filepath:
                    logger.info(f"Screenshot already loaded: {filepath}")
                    return True
            
            # Load the image
            pixmap = QPixmap(str(filepath))
            if pixmap.isNull():
                logger.warning(f"Failed to load pixmap from: {filepath}")
                return False
            
            # Get modification time
            mtime = filepath.stat().st_mtime
            timestamp = datetime.fromtimestamp(mtime)
            
            # Use filename (without extension) as the name
            screenshot_name = filepath.stem
            
            # Add to list widget at the top (newest first)
            item = ScreenshotThumbnail(pixmap, screenshot_name, timestamp)
            item.filepath = filepath
            self.screenshot_list.insertItem(0, item)
            
            # Store the data
            self.screenshots.insert(0, (pixmap, screenshot_name, timestamp, filepath))
            
            # Update counter
            self.screenshot_counter += 1
            
            # Enable export button
            self.export_btn.setEnabled(True)
            
            # Update footer
            self._update_footer()
            
            logger.info(f"Added screenshot from file: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add screenshot from file: {e}")
            return False
    
    def grab_screenshot(self):
        """Capture screenshot of the primary screen"""
        try:
            # Hide this window temporarily
            self.hide()
            
            # Small delay to let window hide
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(200, self._do_screenshot_capture)
            
        except Exception as e:
            logger.error(f"Failed to grab screenshot: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to grab screenshot:\n{e}")
            self.show()
    
    def _do_screenshot_capture(self):
        """Actually perform the screenshot capture"""
        try:
            # Get the primary screen
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            
            if screen:
                # Capture the screenshot
                screenshot = screen.grabWindow(0)
                
                # Increment counter and create name with timestamp for uniqueness
                self.screenshot_counter += 1
                current_time = datetime.now()
                timestamp_str = current_time.strftime('%Y%m%d_%H%M%S')
                time_str = current_time.strftime("%H:%M")
                screenshot_name = f"screenshot_{timestamp_str}"
                
                # Ensure screenshots directory exists
                self.screenshots_dir.mkdir(parents=True, exist_ok=True)
                
                # Save to disk
                filepath = self.screenshots_dir / f"{screenshot_name}.png"
                screenshot.save(str(filepath), 'PNG')
                
                # Add to list
                item = ScreenshotThumbnail(screenshot, screenshot_name, current_time)
                item.filepath = filepath  # Store filepath for deletion
                self.screenshot_list.insertItem(0, item)  # Add at top (newest first)
                
                # Store the data (include filepath)
                self.screenshots.insert(0, (screenshot, screenshot_name, current_time, filepath))
                
                # Update footer count
                self._update_footer()
                
                logger.info(f"Screenshot captured: {screenshot_name}")
            else:
                QMessageBox.warning(self, "Error", "Could not access screen")
        
        except Exception as e:
            logger.error(f"Screenshot capture failed: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Screenshot capture failed:\n{e}")
        
        finally:
            # Show the window again
            self.show()
            self.activateWindow()
            self.raise_()
    
    def capture_active_window(self):
        """Capture only the active/foreground window"""
        try:
            # Hide this window temporarily
            self.hide()
            
            # Small delay to let window hide
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(200, self._do_window_capture)
            
        except Exception as e:
            logger.error(f"Failed to capture window: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to capture window:\n{e}")
            self.show()
    
    def _do_window_capture(self):
        """Actually perform the window capture"""
        try:
            import ctypes
            from ctypes import wintypes
            from PyQt6.QtWidgets import QApplication
            
            # Get foreground window handle using ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            
            if hwnd:
                # Get window rectangle
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                
                x = rect.left
                y = rect.top
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                
                if width > 0 and height > 0:
                    # Grab the window area from screen
                    screen = QApplication.primaryScreen()
                    if screen:
                        screenshot = screen.grabWindow(0, x, y, width, height)
                        
                        # Increment counter and create name with timestamp
                        self.screenshot_counter += 1
                        current_time = datetime.now()
                        timestamp_str = current_time.strftime('%Y%m%d_%H%M%S')
                        screenshot_name = f"window_{timestamp_str}"
                        
                        # Ensure screenshots directory exists
                        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
                        
                        # Save to disk
                        filepath = self.screenshots_dir / f"{screenshot_name}.png"
                        screenshot.save(str(filepath), 'PNG')
                        
                        # Add to list
                        item = ScreenshotThumbnail(screenshot, screenshot_name, current_time)
                        item.filepath = filepath
                        self.screenshot_list.insertItem(0, item)
                        
                        # Store the data
                        self.screenshots.insert(0, (screenshot, screenshot_name, current_time, filepath))
                        
                        # Update footer count
                        self._update_footer()
                        
                        logger.info(f"Window captured: {screenshot_name}")
                    else:
                        QMessageBox.warning(self, "Error", "Could not access screen")
                else:
                    QMessageBox.warning(self, "Error", "Could not get window dimensions")
            else:
                QMessageBox.warning(self, "Error", "Could not find active window")
        
        except Exception as e:
            logger.error(f"Window capture failed: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Window capture failed:\n{e}")
        
        finally:
            # Show the window again
            self.show()
            self.activateWindow()
            self.raise_()
    
    def _toggle_archive_view(self):
        """Toggle between viewing screenshots and archive"""
        self._viewing_archive = self.archive_toggle_btn.isChecked()
        
        if self._viewing_archive:
            self.archive_toggle_btn.setText("📷 Screenshots")
            self.title_label.setText("ARCHIVE")
            self._load_archive_screenshots()
        else:
            self.archive_toggle_btn.setText("📦 Archive")
            self.title_label.setText("SCREENSHOT MANAGER")
            self._load_existing_screenshots()
    
    def _load_archive_screenshots(self):
        """Load screenshots from the archive folder"""
        try:
            # Clear current list
            self.screenshot_list.clear()
            self.screenshots.clear()
            self.viewer_area.clear()
            self.current_viewer_pixmap = None
            
            # Ensure archive directory exists
            self.archive_dir.mkdir(parents=True, exist_ok=True)
            
            # Get all PNG files sorted by modification time (newest first)
            png_files = sorted(
                self.archive_dir.glob("*.png"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            
            for filepath in png_files:
                try:
                    # Load the image
                    pixmap = QPixmap(str(filepath))
                    if pixmap.isNull():
                        continue
                    
                    # Get modification time
                    mtime = filepath.stat().st_mtime
                    timestamp = datetime.fromtimestamp(mtime)
                    
                    # Use filename (without extension) as the name
                    screenshot_name = filepath.stem
                    
                    # Add to list widget
                    item = ScreenshotThumbnail(pixmap, screenshot_name, timestamp)
                    item.filepath = filepath
                    self.screenshot_list.addItem(item)
                    
                    # Store the data
                    self.screenshots.append((pixmap, screenshot_name, timestamp, filepath))
                    
                except Exception as e:
                    logger.warning(f"Failed to load archived screenshot {filepath}: {e}")
            
            # Update footer
            self._update_footer()
            
            if self.screenshots:
                logger.info(f"Loaded {len(self.screenshots)} archived screenshots")
                
        except Exception as e:
            logger.error(f"Failed to load archive: {e}")
    
    def archive_selected_screenshots(self):
        """Move selected screenshots to archive folder"""
        selected_items = list(self.screenshot_list.selectedItems())
        if not selected_items:
            return
        
        # Ensure archive directory exists
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        
        archived_count = 0
        for item in selected_items:
            if isinstance(item, ScreenshotThumbnail) and hasattr(item, 'filepath') and item.filepath:
                try:
                    # Move file to archive
                    src_path = item.filepath
                    dest_path = self.archive_dir / src_path.name
                    
                    # Handle name collision
                    if dest_path.exists():
                        stem = src_path.stem
                        suffix = src_path.suffix
                        counter = 1
                        while dest_path.exists():
                            dest_path = self.archive_dir / f"{stem}_{counter}{suffix}"
                            counter += 1
                    
                    src_path.rename(dest_path)
                    
                    # Remove from list widget
                    row = self.screenshot_list.row(item)
                    self.screenshot_list.takeItem(row)
                    
                    # Remove from screenshots list
                    for i, screenshot_data in enumerate(self.screenshots):
                        if len(screenshot_data) >= 3 and screenshot_data[2] == item.timestamp:
                            self.screenshots.pop(i)
                            break
                    
                    archived_count += 1
                    logger.info(f"Archived screenshot: {src_path.name}")
                    
                except Exception as e:
                    logger.warning(f"Failed to archive {item.filepath}: {e}")
        
        # Clear viewer if archived item was displayed
        if self.current_viewer_pixmap:
            for item in selected_items:
                if isinstance(item, ScreenshotThumbnail) and item.screenshot_pixmap == self.current_viewer_pixmap:
                    self.viewer_area.clear()
                    self.current_viewer_pixmap = None
                    break
        
        # Update footer
        self._update_footer()
        self.status_label.setText(f"Archived {archived_count} screenshot(s)")
    
    def restore_selected_screenshots(self):
        """Restore selected screenshots from archive to main folder"""
        selected_items = list(self.screenshot_list.selectedItems())
        if not selected_items:
            return
        
        restored_count = 0
        for item in selected_items:
            if isinstance(item, ScreenshotThumbnail) and hasattr(item, 'filepath') and item.filepath:
                try:
                    # Move file back to screenshots folder
                    src_path = item.filepath
                    dest_path = self.screenshots_dir / src_path.name
                    
                    # Handle name collision
                    if dest_path.exists():
                        stem = src_path.stem
                        suffix = src_path.suffix
                        counter = 1
                        while dest_path.exists():
                            dest_path = self.screenshots_dir / f"{stem}_{counter}{suffix}"
                            counter += 1
                    
                    src_path.rename(dest_path)
                    
                    # Remove from list widget
                    row = self.screenshot_list.row(item)
                    self.screenshot_list.takeItem(row)
                    
                    # Remove from screenshots list
                    for i, screenshot_data in enumerate(self.screenshots):
                        if len(screenshot_data) >= 3 and screenshot_data[2] == item.timestamp:
                            self.screenshots.pop(i)
                            break
                    
                    restored_count += 1
                    logger.info(f"Restored screenshot: {src_path.name}")
                    
                except Exception as e:
                    logger.warning(f"Failed to restore {item.filepath}: {e}")
        
        # Clear viewer if restored item was displayed
        if self.current_viewer_pixmap:
            for item in selected_items:
                if isinstance(item, ScreenshotThumbnail) and item.screenshot_pixmap == self.current_viewer_pixmap:
                    self.viewer_area.clear()
                    self.current_viewer_pixmap = None
                    break
        
        # Update footer
        self._update_footer()
        self.status_label.setText(f"Restored {restored_count} screenshot(s)")
    
    def display_screenshot(self, item):
        """Display the selected screenshot in the viewer"""
        if isinstance(item, ScreenshotThumbnail):
            # Store pixmap and display directly (scaling handled by setScaledContents)
            pixmap = item.screenshot_pixmap
            self.current_viewer_pixmap = pixmap
            self.viewer_area.setPixmap(pixmap)
    
    def show_context_menu(self, position):
        """Show right-click context menu on screenshot thumbnails"""
        selected_items = self.screenshot_list.selectedItems()
        item = self.screenshot_list.itemAt(position)
        
        if selected_items:
            menu = QMenu(self)
            menu.setStyleSheet("""
                QMenu {
                    background-color: #0D3A7A;
                    border: 1px solid #D4A017;
                    border-radius: 4px;
                    padding: 4px;
                }
                QMenu::item {
                    background-color: transparent;
                    color: white;
                    padding: 6px 20px;
                    font-size: 10px;
                }
                QMenu::item:selected {
                    background-color: #3A7DC8;
                }
                QMenu::separator {
                    height: 1px;
                    background: #D4A017;
                    margin: 4px 8px;
                }
            """)
            
            copy_action = menu.addAction("Copy to Clipboard")
            menu.addSeparator()
            
            # Archive or Restore action depending on current view
            if self._viewing_archive:
                archive_action = menu.addAction(f"📷 Restore ({len(selected_items)})" if len(selected_items) > 1 else "📷 Restore")
            else:
                archive_action = menu.addAction(f"📦 Archive ({len(selected_items)})" if len(selected_items) > 1 else "📦 Archive")
            
            delete_action = menu.addAction(f"🗑 Delete ({len(selected_items)})" if len(selected_items) > 1 else "🗑 Delete")
            menu.addSeparator()
            rename_action = menu.addAction("Rename")
            
            action = menu.exec(self.screenshot_list.mapToGlobal(position))
            
            if action == copy_action:
                # Copy the clicked item (or first selected)
                target = item if item and isinstance(item, ScreenshotThumbnail) else selected_items[0]
                self.copy_to_clipboard(target)
            elif action == archive_action:
                if self._viewing_archive:
                    self.restore_selected_screenshots()
                else:
                    self.archive_selected_screenshots()
            elif action == rename_action:
                # Only rename if single item or clicked on specific item
                if item and isinstance(item, ScreenshotThumbnail):
                    self.rename_screenshot(item)
                elif len(selected_items) == 1:
                    self.rename_screenshot(selected_items[0])
            elif action == delete_action:
                # Delete all selected items
                self.delete_selected_screenshots()
    
    def copy_to_clipboard(self, item):
        """Copy screenshot to clipboard"""
        if isinstance(item, ScreenshotThumbnail):
            try:
                from PyQt6.QtWidgets import QApplication
                clipboard = QApplication.clipboard()
                clipboard.setPixmap(item.screenshot_pixmap)
                logger.info(f"Screenshot '{item.screenshot_name}' copied to clipboard")
            except Exception as e:
                logger.error(f"Failed to copy to clipboard: {e}")
                QMessageBox.warning(self, "Error", f"Failed to copy to clipboard:\n{e}")
    
    def rename_screenshot(self, item):
        """Rename a screenshot"""
        if isinstance(item, ScreenshotThumbnail):
            new_name, ok = QInputDialog.getText(
                self,
                "Rename Screenshot",
                "Enter new name:",
                text=item.screenshot_name
            )
            
            if ok and new_name:
                item.screenshot_name = new_name
                item.setText(new_name)
                
                # Update in screenshots list
                for i, (pixmap, name, timestamp) in enumerate(self.screenshots):
                    if timestamp == item.timestamp:
                        self.screenshots[i] = (pixmap, new_name, timestamp)
                        break
                
                logger.info(f"Screenshot renamed to: {new_name}")
    
    def delete_selected_screenshots(self):
        """Delete all selected screenshots without confirmation"""
        selected_items = list(self.screenshot_list.selectedItems())
        if not selected_items:
            return
        
        for item in selected_items:
            self._delete_single_screenshot(item)
        
        # Update footer after all deletions
        self._update_footer()
        self.status_label.setText(f"Deleted {len(selected_items)} screenshot(s)")
    
    def _delete_single_screenshot(self, item):
        """Delete a single screenshot (internal helper, no confirmation)"""
        if not isinstance(item, ScreenshotThumbnail):
            return
        
        # Remove from list widget
        row = self.screenshot_list.row(item)
        self.screenshot_list.takeItem(row)
        
        # Remove from screenshots list and delete file
        for i, screenshot_data in enumerate(self.screenshots):
            # Handle both old 3-tuple and new 4-tuple formats
            if len(screenshot_data) >= 3:
                timestamp = screenshot_data[2]
                if timestamp == item.timestamp:
                    self.screenshots.pop(i)
                    # Delete file from disk if filepath is stored
                    if len(screenshot_data) >= 4:
                        filepath = screenshot_data[3]
                        try:
                            if filepath and filepath.exists():
                                filepath.unlink()
                                logger.info(f"Deleted screenshot file: {filepath}")
                        except Exception as e:
                            logger.warning(f"Failed to delete file {filepath}: {e}")
                    # Also check if item has filepath attribute
                    elif hasattr(item, 'filepath') and item.filepath:
                        try:
                            if item.filepath.exists():
                                item.filepath.unlink()
                                logger.info(f"Deleted screenshot file: {item.filepath}")
                        except Exception as e:
                            logger.warning(f"Failed to delete file {item.filepath}: {e}")
                    break
        
        # Clear viewer if this was being displayed
        if self.current_viewer_pixmap == item.screenshot_pixmap:
            self.viewer_area.clear()
            self.current_viewer_pixmap = None
        
        logger.info(f"Screenshot deleted: {item.screenshot_name}")
    
    def delete_screenshot(self, item):
        """Delete a single screenshot (no confirmation)"""
        if isinstance(item, ScreenshotThumbnail):
            self._delete_single_screenshot(item)
            self._update_footer()
    
    def update_export_button(self):
        """Enable/disable export button based on selection"""
        self.export_btn.setEnabled(len(self.screenshot_list.selectedItems()) > 0)
    
    def export_screenshots(self):
        """Export selected screenshots to Word or Outlook"""
        selected_items = self.screenshot_list.selectedItems()
        
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select one or more screenshots to export")
            return
        
        export_type = self.export_type_combo.currentText()
        
        try:
            if export_type == "Word":
                self.export_to_word(selected_items)
            elif export_type == "Outlook":
                self.export_to_outlook(selected_items)
        except Exception as e:
            logger.error(f"Export failed: {e}", exc_info=True)
            QMessageBox.warning(self, "Export Error", f"Failed to export screenshots:\n{e}")
    
    def export_to_word(self, items):
        """Export screenshots to a new Word document"""
        try:
            import win32com.client
            
            # Create new Word instance
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = True
            
            # Create new document
            doc = word.Documents.Add()
            
            # Set minimal margins (0.5 inch = 36 points)
            for section in doc.Sections:
                section.PageSetup.LeftMargin = 36
                section.PageSetup.RightMargin = 36
                section.PageSetup.TopMargin = 36
                section.PageSetup.BottomMargin = 36
            
            # Add screenshots
            for item in items:
                if isinstance(item, ScreenshotThumbnail):
                    # Add screenshot name as heading
                    selection = word.Selection
                    selection.Font.Bold = True
                    selection.Font.Size = 12
                    selection.TypeText(item.screenshot_name)
                    selection.TypeParagraph()
                    selection.Font.Bold = False
                    
                    # Save pixmap to temp file
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                        temp_path = tmp.name
                        item.screenshot_pixmap.save(temp_path, 'PNG')
                    
                    # Insert image
                    try:
                        # Get page width to scale image appropriately
                        page_width = doc.PageSetup.PageWidth - doc.PageSetup.LeftMargin - doc.PageSetup.RightMargin
                        
                        inline_shape = selection.InlineShapes.AddPicture(
                            FileName=temp_path,
                            LinkToFile=False,
                            SaveWithDocument=True
                        )
                        
                        # Scale image to fit page width if needed
                        if inline_shape.Width > page_width:
                            aspect_ratio = inline_shape.Height / inline_shape.Width
                            inline_shape.Width = page_width
                            inline_shape.Height = page_width * aspect_ratio
                        
                    finally:
                        # Clean up temp file
                        try:
                            os.unlink(temp_path)
                        except OSError:
                            logger.debug("Ignoring temp screenshot cleanup failure for %s", temp_path, exc_info=True)
                    
                    # Add space after image
                    selection.TypeParagraph()
                    selection.TypeParagraph()
            
            logger.info(f"Exported {len(items)} screenshot(s) to Word")
            self.status_label.setText(f"Exported {len(items)} screenshot(s) to Word")
            
        except Exception as e:
            logger.error(f"Word export failed: {e}", exc_info=True)
            raise
    
    def export_to_outlook(self, items):
        """Export screenshots to a new Outlook email"""
        try:
            import win32com.client
            
            # Create Outlook instance
            outlook = win32com.client.Dispatch("Outlook.Application")
            
            # Create new email
            mail = outlook.CreateItem(0)  # 0 = olMailItem
            
            # Build HTML body with screenshots
            html_body = "<html><body>"
            
            # Temporary files list to clean up later
            temp_files = []
            
            for item in items:
                if isinstance(item, ScreenshotThumbnail):
                    # Add screenshot name as heading
                    html_body += f"<p><strong>{item.screenshot_name}</strong></p>"
                    
                    # Save pixmap to temp file
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                        temp_path = tmp.name
                        item.screenshot_pixmap.save(temp_path, 'PNG')
                        temp_files.append(temp_path)
                    
                    # Add image as attachment and embed in HTML
                    attachment = mail.Attachments.Add(temp_path)
                    
                    # Set content ID for embedding
                    cid = f"screenshot_{len(temp_files)}"
                    attachment.PropertyAccessor.SetProperty(
                        "http://schemas.microsoft.com/mapi/proptag/0x3712001F",
                        cid
                    )
                    
                    # Get image dimensions and scale to 25%
                    img_width = item.screenshot_pixmap.width() // 4
                    img_height = item.screenshot_pixmap.height() // 4
                    
                    # Embed image in HTML with scaled dimensions
                    html_body += f'<p><img src="cid:{cid}" width="{img_width}" height="{img_height}" /></p>'
                    
                    # Add space
                    html_body += "<p>&nbsp;</p>"
            
            html_body += "</body></html>"
            
            # Set email body
            mail.HTMLBody = html_body
            
            # Display the email
            mail.Display()
            
            logger.info(f"Exported {len(items)} screenshot(s) to Outlook")
            self.status_label.setText(f"Exported {len(items)} screenshot(s) to Outlook")
            
        except Exception as e:
            logger.error(f"Outlook export failed: {e}", exc_info=True)
            raise
    