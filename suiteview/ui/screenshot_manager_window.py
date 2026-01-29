"""
SuiteView - Screen Shot Manager
Capture, organize, and export screenshots
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                              QLabel, QListWidget, QListWidgetItem, QMenu, 
                              QInputDialog, QMessageBox, QComboBox, QFrame,
                              QSizePolicy, QAbstractItemView, QSplitter, QApplication)
from PyQt6.QtCore import Qt, QSize, QByteArray, QBuffer, QIODevice, QMimeData, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon, QScreen, QPainter, QColor, QPen, QDrag, QBrush, QLinearGradient, QFont

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


class ScreenShotManagerWindow(QWidget):
    """Screen Shot Manager with capture, organize, and export functionality"""
    
    # Signal emitted when a new screenshot is added (for external listeners)
    screenshot_added = pyqtSignal(str)  # Emits filepath
    
    def __init__(self):
        super().__init__()
        
        # Frameless window setup
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        
        # Enable mouse tracking for resize cursor updates
        self.setMouseTracking(True)
        
        # Drag tracking
        self._drag_pos = None
        self._is_maximized = False
        
        # Resize edge detection
        self._resize_margin = 6
        self._resizing = False
        self._resize_edge = None
        self._start_geometry = None
        
        self.screenshots = []  # List of (pixmap, name, timestamp, filepath) tuples
        self.screenshot_counter = 0
        self.current_viewer_pixmap = None
        self.screenshots_dir = Path.home() / '.suiteview' / 'screenshots'
        
        self.init_ui()
        self._load_existing_screenshots()
        logger.info("Screenshot Manager initialized")
    
    def init_ui(self):
        """Initialize the UI with SuiteView theme and frameless window"""
        self.setWindowTitle("SuiteView - Screenshot Manager")
        self.resize(900, 500)
        
        # Set gold border on the window
        self.setStyleSheet("""
            ScreenShotManagerWindow {
                background-color: #0D3A7A;
                border: 3px solid #D4A017;
                border-radius: 4px;
            }
        """)
        
        # Main layout - margins match border width
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(3, 3, 3, 3)
        main_layout.setSpacing(0)
        
        # Header bar - custom title bar with window controls
        self.header_bar = QFrame()
        self.header_bar.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1E5BA8, stop:0.5 #0D3A7A, stop:1 #082B5C);
                border: none;
                border-bottom: 2px solid #D4A017;
            }
        """)
        self.header_bar.setFixedHeight(36)
        
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(8)
        
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
        header_layout.addWidget(self.grab_btn)
        
        # Title in center
        self.title_label = QLabel("SCREENSHOT MANAGER")
        self.title_label.setStyleSheet("""
            QLabel {
                color: #D4A017;
                font-size: 10pt;
                font-weight: 700;
                letter-spacing: 1px;
                background: transparent;
            }
        """)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.title_label, stretch=1)
        
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
        header_layout.addWidget(self.export_type_combo)
        
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
        header_layout.addWidget(self.export_btn)
        
        header_layout.addSpacing(16)
        
        # Window control buttons
        btn_style = """
            QPushButton {
                background: transparent;
                border: none;
                color: #D4A017;
                font-size: 14px;
                font-weight: bold;
                padding: 2px 8px;
            }
            QPushButton:hover {
                background: rgba(212, 160, 23, 0.3);
                border-radius: 2px;
            }
        """
        close_btn_style = """
            QPushButton {
                background: transparent;
                border: none;
                color: #D4A017;
                font-size: 14px;
                font-weight: bold;
                padding: 2px 8px;
            }
            QPushButton:hover {
                background: #c42b1c;
                color: white;
                border-radius: 2px;
            }
        """
        
        self.minimize_btn = QPushButton("─")
        self.minimize_btn.setFixedSize(32, 26)
        self.minimize_btn.setStyleSheet(btn_style)
        self.minimize_btn.clicked.connect(self.showMinimized)
        header_layout.addWidget(self.minimize_btn)
        
        self.maximize_btn = QPushButton("☐")
        self.maximize_btn.setFixedSize(32, 26)
        self.maximize_btn.setStyleSheet(btn_style)
        self.maximize_btn.clicked.connect(self._toggle_maximize)
        header_layout.addWidget(self.maximize_btn)
        
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(32, 26)
        self.close_btn.setStyleSheet(close_btn_style)
        self.close_btn.clicked.connect(self.close)
        header_layout.addWidget(self.close_btn)
        
        main_layout.addWidget(self.header_bar)
        
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
        self.viewer_area.setScaledContents(False)
        self.viewer_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
    
    def _load_existing_screenshots(self):
        """Load existing screenshots from the screenshots folder"""
        try:
            if not self.screenshots_dir.exists():
                self.screenshots_dir.mkdir(parents=True, exist_ok=True)
                return
            
            # Get all PNG files sorted by modification time (newest first)
            png_files = sorted(
                self.screenshots_dir.glob("*.png"),
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
    
    def display_screenshot(self, item):
        """Display the selected screenshot in the viewer"""
        if isinstance(item, ScreenshotThumbnail):
            # Scale the screenshot to fit the viewer while maintaining aspect ratio
            pixmap = item.screenshot_pixmap
            self.current_viewer_pixmap = pixmap
            
            # Scale to fit viewer area
            scaled_pixmap = pixmap.scaled(
                self.viewer_area.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.viewer_area.setPixmap(scaled_pixmap)
    
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
            delete_action = menu.addAction(f"Delete ({len(selected_items)})" if len(selected_items) > 1 else "Delete")
            menu.addSeparator()
            rename_action = menu.addAction("Rename")
            
            action = menu.exec(self.screenshot_list.mapToGlobal(position))
            
            if action == copy_action:
                # Copy the clicked item (or first selected)
                target = item if item and isinstance(item, ScreenshotThumbnail) else selected_items[0]
                self.copy_to_clipboard(target)
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
            from win32com.client import constants
            
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
                        except:
                            pass
                    
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
    
    def resizeEvent(self, event):
        """Handle window resize to update viewer"""
        # Don't process resize events during manual resize to avoid feedback loop
        if self._resizing:
            event.accept()
            return
        
        super().resizeEvent(event)
        
        # Update viewer if there's a screenshot displayed
        if self.current_viewer_pixmap:
            scaled_pixmap = self.current_viewer_pixmap.scaled(
                self.viewer_area.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.viewer_area.setPixmap(scaled_pixmap)
    
    def _toggle_maximize(self):
        """Toggle between maximized and normal window state"""
        if self._is_maximized:
            self.showNormal()
            self.maximize_btn.setText("☐")
            self._is_maximized = False
        else:
            self.showMaximized()
            self.maximize_btn.setText("❐")
            self._is_maximized = True
    
    def _get_resize_edge(self, pos):
        """Determine which edge (if any) the mouse is near for resizing"""
        margin = self._resize_margin
        rect = self.rect()
        
        on_left = pos.x() <= margin
        on_right = pos.x() >= rect.width() - margin
        on_top = pos.y() <= margin
        on_bottom = pos.y() >= rect.height() - margin
        
        if on_top and on_left:
            return 'top-left'
        elif on_top and on_right:
            return 'top-right'
        elif on_bottom and on_left:
            return 'bottom-left'
        elif on_bottom and on_right:
            return 'bottom-right'
        elif on_left:
            return 'left'
        elif on_right:
            return 'right'
        elif on_top:
            return 'top'
        elif on_bottom:
            return 'bottom'
        return None
    
    def _update_cursor_for_edge(self, edge):
        """Update cursor based on resize edge"""
        cursors = {
            'left': Qt.CursorShape.SizeHorCursor,
            'right': Qt.CursorShape.SizeHorCursor,
            'top': Qt.CursorShape.SizeVerCursor,
            'bottom': Qt.CursorShape.SizeVerCursor,
            'top-left': Qt.CursorShape.SizeFDiagCursor,
            'bottom-right': Qt.CursorShape.SizeFDiagCursor,
            'top-right': Qt.CursorShape.SizeBDiagCursor,
            'bottom-left': Qt.CursorShape.SizeBDiagCursor,
        }
        if edge in cursors:
            self.setCursor(cursors[edge])
        else:
            self.unsetCursor()
    
    def mousePressEvent(self, event):
        """Handle mouse press for dragging and resizing"""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            
            # Check if we're on a resize edge
            edge = self._get_resize_edge(pos)
            if edge and not self._is_maximized:
                self._resizing = True
                self._resize_edge = edge
                self._drag_pos = event.globalPosition().toPoint()
                self._start_geometry = self.geometry()
                event.accept()
                return
            
            # Check if we're in the header bar (for dragging)
            header_rect = self.header_bar.geometry()
            if header_rect.contains(pos):
                # Don't drag if clicking on buttons
                widget_at = self.childAt(pos)
                if isinstance(widget_at, QPushButton):
                    super().mousePressEvent(event)
                    return
                
                self._drag_pos = event.globalPosition().toPoint()
                event.accept()
                return
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging and resizing"""
        pos = event.pos()
        
        # Update cursor when not pressing
        if not event.buttons():
            edge = self._get_resize_edge(pos)
            self._update_cursor_for_edge(edge)
            super().mouseMoveEvent(event)
            return
        
        if event.buttons() == Qt.MouseButton.LeftButton:
            # Handle resizing
            if self._resizing and self._resize_edge:
                delta = event.globalPosition().toPoint() - self._drag_pos
                geo = self._start_geometry
                
                new_x, new_y = geo.x(), geo.y()
                new_w, new_h = geo.width(), geo.height()
                min_w, min_h = 200, 50  # Allow shrinking to just the header
                
                if 'left' in self._resize_edge:
                    new_w = max(min_w, geo.width() - delta.x())
                    if new_w > min_w:
                        new_x = geo.x() + delta.x()
                if 'right' in self._resize_edge:
                    new_w = max(min_w, geo.width() + delta.x())
                if 'top' in self._resize_edge:
                    new_h = max(min_h, geo.height() - delta.y())
                    if new_h > min_h:
                        new_y = geo.y() + delta.y()
                if 'bottom' in self._resize_edge:
                    new_h = max(min_h, geo.height() + delta.y())
                
                self.setGeometry(new_x, new_y, new_w, new_h)
                event.accept()
                return
            
            # Handle dragging
            if self._drag_pos is not None and not self._resizing:
                # If maximized, restore and center on cursor
                if self._is_maximized:
                    self._is_maximized = False
                    self.showNormal()
                    self.maximize_btn.setText("☐")
                    # Reposition so cursor is centered on title bar
                    new_geo = self.geometry()
                    self._drag_pos = event.globalPosition().toPoint()
                    self.move(
                        self._drag_pos.x() - new_geo.width() // 2,
                        self._drag_pos.y() - 20
                    )
                else:
                    delta = event.globalPosition().toPoint() - self._drag_pos
                    self.move(self.pos() + delta)
                    self._drag_pos = event.globalPosition().toPoint()
                event.accept()
                return
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release"""
        self._drag_pos = None
        self._resizing = False
        self._resize_edge = None
        super().mouseReleaseEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """Handle double-click on title bar to maximize/restore"""
        if event.button() == Qt.MouseButton.LeftButton:
            header_rect = self.header_bar.geometry()
            if header_rect.contains(event.pos()):
                # Don't toggle if clicking on buttons
                widget_at = self.childAt(event.pos())
                if not isinstance(widget_at, QPushButton):
                    self._toggle_maximize()
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)