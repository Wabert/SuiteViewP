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
                              QSizePolicy, QAbstractItemView, QSplitter)
from PyQt6.QtCore import Qt, QSize, QByteArray, QBuffer, QIODevice, QMimeData
from PyQt6.QtGui import QPixmap, QIcon, QScreen, QPainter, QColor, QPen, QDrag

logger = logging.getLogger(__name__)


class ScreenshotThumbnail(QListWidgetItem):
    """Custom list item for screenshot thumbnail with metadata"""
    
    def __init__(self, screenshot_pixmap, screenshot_name, timestamp):
        super().__init__()
        self.screenshot_pixmap = screenshot_pixmap
        self.screenshot_name = screenshot_name
        self.timestamp = timestamp
        
        # Create thumbnail
        thumbnail = screenshot_pixmap.scaled(
            100, 75,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.setIcon(QIcon(thumbnail))
        self.setText(screenshot_name)
        self.setSizeHint(QSize(120, 95))


class ScreenshotListWidget(QListWidget):
    """Custom list widget with drag-and-drop reordering support"""
    
    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(100, 75))
        self.setSpacing(10)
        self.setMovement(QListWidget.Movement.Snap)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setWrapping(True)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setGridSize(QSize(120, 100))
        
        # Style
        self.setStyleSheet("""
            QListWidget {
                background-color: #cce5ff;
                border: 2px solid #0078d4;
                border-radius: 5px;
                padding: 5px;
            }
            QListWidget::item {
                background-color: white;
                border: 2px solid #ffa500;
                border-radius: 8px;
                padding: 5px;
                margin: 5px;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                border: 3px solid #0078d4;
            }
            QListWidget::item:hover {
                background-color: #f0f8ff;
            }
        """)


class ScreenShotManagerWindow(QWidget):
    """Screen Shot Manager with capture, organize, and export functionality"""
    
    def __init__(self):
        super().__init__()
        self.screenshots = []  # List of (pixmap, name, timestamp) tuples
        self.screenshot_counter = 0
        self.current_viewer_pixmap = None
        
        self.init_ui()
        logger.info("Screenshot Manager initialized")
    
    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle("SuiteView - Screen Shot Manager")
        self.resize(1000, 600)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Title bar with blue background and gold border
        title_bar = QFrame()
        title_bar.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                           stop:0 #2563EB, stop:0.5 #1E3A8A, stop:1 #2563EB);
                border: 3px solid #D4AF37;
                border-radius: 0px;
                padding: 5px;
            }
        """)
        title_bar.setFixedHeight(60)
        
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(10, 5, 10, 5)
        
        # Grab button on the left
        self.grab_btn = QPushButton("Grab")
        self.grab_btn.setFixedSize(80, 40)
        self.grab_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #1E3A8A;
                border: 2px solid #D4AF37;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #ffd700;
                color: #000000;
            }
            QPushButton:pressed {
                background-color: #D4AF37;
            }
        """)
        self.grab_btn.clicked.connect(self.grab_screenshot)
        title_layout.addWidget(self.grab_btn)
        
        # Title in center
        title_label = QLabel("SuiteView - Screen Shot Manager")
        title_label.setStyleSheet("""
            QLabel {
                color: #D4AF37;
                font-size: 18px;
                font-weight: bold;
                border: none;
            }
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(title_label, stretch=1)
        
        # Export controls on the right
        export_layout = QHBoxLayout()
        export_layout.setSpacing(10)
        
        # Export button
        self.export_btn = QPushButton("Export")
        self.export_btn.setFixedSize(80, 40)
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #1E3A8A;
                border: 2px solid #D4AF37;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #ffd700;
                color: #000000;
            }
            QPushButton:pressed {
                background-color: #D4AF37;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
                border: 2px solid #999999;
            }
        """)
        self.export_btn.clicked.connect(self.export_screenshots)
        self.export_btn.setEnabled(False)
        export_layout.addWidget(self.export_btn)
        
        # Export type combo box
        self.export_type_combo = QComboBox()
        self.export_type_combo.addItems(["Word", "Outlook"])
        self.export_type_combo.setFixedSize(100, 40)
        self.export_type_combo.setStyleSheet("""
            QComboBox {
                background-color: #ffffff;
                color: #1E3A8A;
                border: 2px solid #D4AF37;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
                padding: 5px;
            }
            QComboBox:hover {
                background-color: #ffd700;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                selection-background-color: #0078d4;
                selection-color: white;
            }
        """)
        export_layout.addWidget(self.export_type_combo)
        
        title_layout.addLayout(export_layout)
        
        main_layout.addWidget(title_bar)
        
        # Content area - horizontal splitter for resizable panels
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.setHandleWidth(8)
        content_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #D4AF37;
                margin: 2px 0px;
            }
            QSplitter::handle:horizontal {
                width: 8px;
            }
            QSplitter::handle:hover {
                background-color: #ffd700;
            }
        """)
        
        # Left panel - Screenshots list
        left_panel = QFrame()
        left_panel.setStyleSheet("""
            QFrame {
                background-color: #f0f0f0;
                border: 2px solid #0078d4;
                border-radius: 5px;
            }
        """)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        left_layout.setSpacing(5)
        
        # Screenshots label
        screenshots_label = QLabel("Screen Shots")
        screenshots_label.setStyleSheet("""
            QLabel {
                color: #1E3A8A;
                font-size: 14px;
                font-weight: bold;
                background-color: transparent;
                border: none;
            }
        """)
        screenshots_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        screenshots_label.setFixedHeight(25)
        left_layout.addWidget(screenshots_label)
        
        # Screenshot list
        self.screenshot_list = ScreenshotListWidget()
        self.screenshot_list.itemClicked.connect(self.display_screenshot)
        self.screenshot_list.itemSelectionChanged.connect(self.update_export_button)
        self.screenshot_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.screenshot_list.customContextMenuRequested.connect(self.show_context_menu)
        left_layout.addWidget(self.screenshot_list)
        
        content_splitter.addWidget(left_panel)
        
        # Right panel - Viewer
        right_panel = QFrame()
        right_panel.setStyleSheet("""
            QFrame {
                background-color: #f0f0f0;
                border: 2px solid #0078d4;
                border-radius: 5px;
            }
        """)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 5, 5, 5)
        right_layout.setSpacing(5)
        
        # Viewer label
        viewer_label = QLabel("VIEWER")
        viewer_label.setStyleSheet("""
            QLabel {
                color: #1E3A8A;
                font-size: 14px;
                font-weight: bold;
                background-color: transparent;
                border: none;
            }
        """)
        viewer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        viewer_label.setFixedHeight(25)
        right_layout.addWidget(viewer_label)
        
        # Viewer area
        self.viewer_area = QLabel()
        self.viewer_area.setStyleSheet("""
            QLabel {
                background-color: #e3f2fd;
                border: 2px solid #0078d4;
                border-radius: 5px;
            }
        """)
        self.viewer_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewer_area.setScaledContents(False)
        self.viewer_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_layout.addWidget(self.viewer_area, 1)
        
        content_splitter.addWidget(right_panel)
        
        # Set initial sizes for splitter (300px for left, rest for right)
        content_splitter.setSizes([300, 700])
        
        main_layout.addWidget(content_splitter)
        
        # Bottom status bar with gold border
        status_bar = QFrame()
        status_bar.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                           stop:0 #2563EB, stop:0.5 #1E3A8A, stop:1 #2563EB);
                border: 3px solid #D4AF37;
                border-radius: 0px;
                padding: 3px;
            }
        """)
        status_bar.setFixedHeight(30)
        main_layout.addWidget(status_bar)
    
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
                
                # Increment counter and create name
                self.screenshot_counter += 1
                current_time = datetime.now()
                time_str = current_time.strftime("%H:%M")
                screenshot_name = f"{self.screenshot_counter} {time_str}"
                
                # Add to list
                item = ScreenshotThumbnail(screenshot, screenshot_name, current_time)
                self.screenshot_list.addItem(item)
                
                # Store the data
                self.screenshots.append((screenshot, screenshot_name, current_time))
                
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
        item = self.screenshot_list.itemAt(position)
        if item and isinstance(item, ScreenshotThumbnail):
            menu = QMenu(self)
            
            copy_action = menu.addAction("Copy to Clipboard")
            menu.addSeparator()
            rename_action = menu.addAction("Rename")
            delete_action = menu.addAction("Delete")
            
            action = menu.exec(self.screenshot_list.mapToGlobal(position))
            
            if action == copy_action:
                self.copy_to_clipboard(item)
            elif action == rename_action:
                self.rename_screenshot(item)
            elif action == delete_action:
                self.delete_screenshot(item)
    
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
    
    def delete_screenshot(self, item):
        """Delete a screenshot"""
        if isinstance(item, ScreenshotThumbnail):
            reply = QMessageBox.question(
                self,
                "Delete Screenshot",
                f"Are you sure you want to delete '{item.screenshot_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Remove from list widget
                row = self.screenshot_list.row(item)
                self.screenshot_list.takeItem(row)
                
                # Remove from screenshots list
                for i, (pixmap, name, timestamp) in enumerate(self.screenshots):
                    if timestamp == item.timestamp:
                        self.screenshots.pop(i)
                        break
                
                # Clear viewer if this was being displayed
                if self.current_viewer_pixmap == item.screenshot_pixmap:
                    self.viewer_area.clear()
                    self.current_viewer_pixmap = None
                
                logger.info(f"Screenshot deleted: {item.screenshot_name}")
    
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
            QMessageBox.information(self, "Export Complete", f"Exported {len(items)} screenshot(s) to Word")
            
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
                    
                    # Embed image in HTML
                    html_body += f'<p><img src="cid:{cid}" /></p>'
                    
                    # Add space
                    html_body += "<p>&nbsp;</p>"
            
            html_body += "</body></html>"
            
            # Set email body
            mail.HTMLBody = html_body
            
            # Display the email
            mail.Display()
            
            logger.info(f"Exported {len(items)} screenshot(s) to Outlook")
            QMessageBox.information(self, "Export Complete", f"Exported {len(items)} screenshot(s) to Outlook email")
            
        except Exception as e:
            logger.error(f"Outlook export failed: {e}", exc_info=True)
            raise
    
    def resizeEvent(self, event):
        """Handle window resize to update viewer"""
        super().resizeEvent(event)
        
        # Update viewer if there's a screenshot displayed
        if self.current_viewer_pixmap:
            scaled_pixmap = self.current_viewer_pixmap.scaled(
                self.viewer_area.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.viewer_area.setPixmap(scaled_pixmap)
