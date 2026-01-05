"""
Email Attachment Manager - Find, filter, and manage email attachments

Features:
- View all email attachments with metadata (subject, sender, date, name, type, size)
- Filter and sort by any column
- Global search across all fields
- Double-click email subject to open email in Outlook
- Double-click attachment name to open attachment
- Multi-select and copy attachments to Downloads folder
- Detect duplicate attachments by hash
- Timeline view of attachment activity
- Quick preview for images and PDFs
- Archive attachments to disk with email link preservation
"""

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTabWidget, QMessageBox, QFileDialog, QDialog, QTextEdit,
    QSplitter, QListWidget, QListWidgetItem, QProgressDialog, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QPixmap

import pandas as pd

from suiteview.ui.widgets.filter_table_view import FilterTableView
from suiteview.core.outlook_manager import get_outlook_manager
from suiteview.data.repositories import get_email_repository

logger = logging.getLogger(__name__)


class ImagePreviewDialog(QDialog):
    """Dialog for quick image preview"""
    
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Preview")
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        # Image label
        from PyQt6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        image_label = QLabel()
        pixmap = QPixmap(image_path)
        
        # Scale if too large
        if pixmap.width() > 1200 or pixmap.height() > 900:
            pixmap = pixmap.scaled(1200, 900, Qt.AspectRatioMode.KeepAspectRatio, 
                                  Qt.TransformationMode.SmoothTransformation)
        
        image_label.setPixmap(pixmap)
        scroll.setWidget(image_label)
        
        layout.addWidget(scroll)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class EmailAttachmentManager(QWidget):
    """Email Attachment Manager main window"""
    
    def __init__(self, parent=None, launcher=None):
        super().__init__(parent)
        
        self.launcher = launcher  # Reference to launcher for opening File Navigator
        self.outlook = get_outlook_manager()
        self.repo = get_email_repository()
        
        self.setWindowTitle("SuiteView - Attachment Manager")
        self.resize(1400, 800)
        
        self.init_ui()
        self.load_data()
    
    def init_ui(self):
        """Initialize UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Title bar
        title_layout = QHBoxLayout()
        
        title = QLabel("📎 Attachment Manager")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title_layout.addWidget(title)
        
        title_layout.addStretch()
        
        layout.addLayout(title_layout)
        
        # Tab widget for different views
        self.tabs = QTabWidget()
        
        # All Attachments tab
        self.all_attachments_tab = self.create_all_attachments_tab()
        self.tabs.addTab(self.all_attachments_tab, "All Attachments")
        
        # Duplicates tab
        self.duplicates_tab = self.create_duplicates_tab()
        self.tabs.addTab(self.duplicates_tab, "Duplicates")
        
        # Timeline tab
        self.timeline_tab = self.create_timeline_tab()
        self.tabs.addTab(self.timeline_tab, "Timeline")
        
        layout.addWidget(self.tabs)
    
    def create_all_attachments_tab(self):
        """Create All Attachments tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(5)
        
        # Common button style
        button_style = """
            QPushButton {
                background-color: #f5f5f5;
                color: #000000;
                border: 1px solid #cccccc;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
                border-color: #999999;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
        """
        
        # Action buttons
        self.open_email_btn = QPushButton("Open Email")
        self.open_email_btn.setFixedHeight(28)
        self.open_email_btn.setStyleSheet(button_style)
        self.open_email_btn.clicked.connect(self.open_selected_email)
        toolbar.addWidget(self.open_email_btn)
        
        self.open_attachment_btn = QPushButton("Open Attachment")
        self.open_attachment_btn.setFixedHeight(28)
        self.open_attachment_btn.setStyleSheet(button_style)
        self.open_attachment_btn.clicked.connect(self.open_selected_attachment)
        toolbar.addWidget(self.open_attachment_btn)
        
        self.preview_btn = QPushButton("Preview")
        self.preview_btn.setFixedHeight(28)
        self.preview_btn.setStyleSheet(button_style)
        self.preview_btn.clicked.connect(self.preview_selected_attachment)
        toolbar.addWidget(self.preview_btn)
        
        toolbar.addStretch()
        
        self.copy_to_downloads_btn = QPushButton("Copy to Downloads")
        self.copy_to_downloads_btn.setFixedHeight(28)
        self.copy_to_downloads_btn.setStyleSheet(button_style)
        self.copy_to_downloads_btn.clicked.connect(self.copy_selected_to_downloads)
        toolbar.addWidget(self.copy_to_downloads_btn)
        
        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.setFixedHeight(28)
        self.open_folder_btn.setStyleSheet(button_style)
        self.open_folder_btn.clicked.connect(self.open_downloads_folder)
        toolbar.addWidget(self.open_folder_btn)
        
        self.archive_btn = QPushButton("Archive...")
        self.archive_btn.setFixedHeight(28)
        self.archive_btn.setStyleSheet(button_style)
        self.archive_btn.clicked.connect(self.archive_selected_attachments)
        toolbar.addWidget(self.archive_btn)
        
        layout.addLayout(toolbar)
        
        # Attachments grid using FilterTableView
        self.attachments_grid = FilterTableView()
        layout.addWidget(self.attachments_grid)
        
        # Connect double-click handler (access table_view directly)
        if hasattr(self.attachments_grid, 'table_view'):
            self.attachments_grid.table_view.doubleClicked.connect(self.on_attachment_double_click)
        
        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #666; padding: 3px;")
        layout.addWidget(self.status_label)
        
        return tab
    
    def create_duplicates_tab(self):
        """Create Duplicates tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Info label
        info = QLabel("Duplicate attachments detected by file hash (MD5)")
        info.setStyleSheet("color: #666; padding: 5px;")
        layout.addWidget(info)
        
        # Duplicates grid
        self.duplicates_grid = FilterTableView()
        layout.addWidget(self.duplicates_grid)
        
        # Details section
        details_label = QLabel("Select a duplicate group to see details:")
        layout.addWidget(details_label)
        
        self.duplicate_details_list = QListWidget()
        self.duplicate_details_list.setMaximumHeight(150)
        layout.addWidget(self.duplicate_details_list)
        
        return tab
    
    def create_timeline_tab(self):
        """Create Timeline tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Info label
        info = QLabel("Attachments grouped by date")
        info.setStyleSheet("color: #666; padding: 5px;")
        layout.addWidget(info)
        
        # Timeline grid
        self.timeline_grid = FilterTableView()
        layout.addWidget(self.timeline_grid)
        
        return tab
    
    def load_data(self):
        """Load attachment data from repository"""
        # Load all attachments
        attachments = self.repo.get_all_attachments()
        
        if not attachments:
            self.status_label.setText("No attachments found. Run a sync from Email Navigator first.")
            return
        
        # Convert to DataFrame
        df = pd.DataFrame(attachments)
        
        # Format size to be human readable
        df['size_mb'] = df['attachment_size'].apply(lambda x: f"{x / (1024*1024):.2f}")
        
        # Format date - use ISO8601 format to handle varying date formats
        df['date'] = pd.to_datetime(df['email_date'], format='ISO8601').dt.strftime('%Y-%m-%d %H:%M')
        
        # Select and rename columns for display
        display_df = df[[
            'email_subject', 'email_sender', 'date', 'attachment_name',
            'attachment_type', 'size_mb'
        ]].copy()
        
        display_df.columns = [
            'Email Subject', 'Sender', 'Date', 'Attachment Name',
            'Type', 'Size (MB)'
        ]
        
        # Store original data for lookups
        self.attachment_data = df
        
        # Load into grid
        self.attachments_grid.set_dataframe(display_df)
        
        self.status_label.setText(f"Loaded {len(attachments)} attachments")
        
        # Load duplicates
        self.load_duplicates()
        
        # Load timeline
        self.load_timeline()
    
    def reconnect_outlook(self):
        """Attempt to reconnect to Outlook"""
        # Try to reconnect
        success = self.outlook.reconnect()
        
        if success:
            QMessageBox.information(
                self,
                "Outlook Connected",
                "Successfully connected to Outlook!\n\n"
                "You can now open attachments."
            )
        else:
            QMessageBox.warning(
                self,
                "Connection Failed",
                "Failed to connect to Outlook.\n\n"
                "Please ensure:\n"
                "1. Microsoft Outlook is installed\n"
                "2. Outlook is running (try starting it manually)\n"
                "3. You have permission to access Outlook\n\n"
                "After starting Outlook, click 'Reconnect Outlook' again."
            )
    
    def load_duplicates(self):
        """Load duplicate attachments"""
        duplicates = self.repo.get_duplicate_attachments()
        
        if not duplicates:
            return
        
        # Convert to DataFrame
        df = pd.DataFrame(duplicates)
        
        # Calculate wasted space
        df['wasted_mb'] = df['total_size'].apply(lambda x: f"{(x / (1024*1024)):.2f}")
        
        # Select columns
        display_df = df[['file_hash', 'count', 'wasted_mb']].copy()
        display_df.columns = ['File Hash', 'Duplicate Count', 'Wasted Space (MB)']
        
        self.duplicates_grid.set_dataframe(display_df)
    
    def load_timeline(self):
        """Load timeline view"""
        if not hasattr(self, 'attachment_data') or self.attachment_data.empty:
            return
        
        # Group by date
        df = self.attachment_data.copy()
        df['date_only'] = pd.to_datetime(df['email_date'], format='ISO8601').dt.date
        
        timeline = df.groupby('date_only').agg({
            'attachment_name': 'count',
            'attachment_size': 'sum'
        }).reset_index()
        
        timeline.columns = ['Date', 'Attachment Count', 'Total Size']
        timeline['Total Size (MB)'] = timeline['Total Size'].apply(lambda x: f"{x / (1024*1024):.2f}")
        timeline = timeline.drop('Total Size', axis=1)
        timeline = timeline.sort_values('Date', ascending=False)
        
        self.timeline_grid.set_dataframe(timeline)
    
    def on_attachment_double_click(self, index):
        """Handle double-click on attachment grid"""
        # Get the column that was clicked
        col = index.column()
        row = index.row()
        
        # Map filtered view row to original data row
        if hasattr(self.attachments_grid, 'model') and self.attachments_grid.model:
            display_indices = self.attachments_grid.model._display_indices
            if row < 0 or row >= len(display_indices):
                return
            actual_index = display_indices[row]
            attachment = self.attachment_data.loc[actual_index]
        else:
            # Fallback if no filtering is active
            if row < 0 or row >= len(self.attachment_data):
                return
            attachment = self.attachment_data.iloc[row]
        
        # Column 0 is Email Subject - open email
        if col == 0:
            self.open_email(attachment['email_id'])
        # Column 3 is Attachment Name - open attachment
        elif col == 3:
            self.open_attachment(attachment['email_id'], attachment['attachment_index'])
    
    def open_selected_email(self):
        """Open selected email in Outlook"""
        selected = self.get_selected_attachments()
        
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select an attachment first")
            return
        
        # Open first selected email
        self.open_email(selected[0]['email_id'])
    
    def open_email(self, email_id: str):
        """Open email in Outlook"""
        if not self.outlook.is_connected():
            # Show helpful error with reconnect option
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Outlook Not Connected")
            msg.setText("Not connected to Outlook")
            msg.setInformativeText(
                "To open emails, Outlook must be connected.\n\n"
                "Please ensure Microsoft Outlook is running, then click 'Reconnect'."
            )
            reconnect_btn = msg.addButton("Reconnect", QMessageBox.ButtonRole.AcceptRole)
            cancel_btn = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            
            if msg.clickedButton() == reconnect_btn:
                self.reconnect_outlook()
            return
        
        success = self.outlook.open_email(email_id)
        
        if not success:
            QMessageBox.warning(self, "Error", "Failed to open email")
    
    def open_selected_attachment(self):
        """Open selected attachment"""
        selected = self.get_selected_attachments()
        
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select an attachment first")
            return
        
        # Open first selected attachment
        attach = selected[0]
        self.open_attachment(attach['email_id'], attach['attachment_index'])
    
    def open_attachment(self, email_id: str, attachment_index: int):
        """Open attachment with default application"""
        if not self.outlook.is_connected():
            # Show helpful error with reconnect option
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Outlook Not Connected")
            msg.setText("Not connected to Outlook")
            msg.setInformativeText(
                "To open attachments, Outlook must be connected.\n\n"
                "Please ensure Microsoft Outlook is running, then try reconnecting."
            )
            msg.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
            msg.exec()
            return
        
        # Show progress cursor
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        
        try:
            # Get temp path (runs on main thread - required for COM)
            temp_path = self.outlook.get_attachment_preview_path(email_id, attachment_index)
            
            QApplication.restoreOverrideCursor()
            
            if temp_path and os.path.exists(temp_path):
                os.startfile(temp_path)
            else:
                QMessageBox.warning(self, "Error", "Failed to retrieve attachment")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Error", f"Failed to open attachment: {e}")
    
    def preview_selected_attachment(self):
        """Preview selected attachment (for images/PDFs)"""
        selected = self.get_selected_attachments()
        
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select an attachment first")
            return
        
        attach = selected[0]
        
        # Check if it's an image
        image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp']
        if attach['attachment_type'].lower() not in image_exts:
            QMessageBox.information(
                self, "Preview", 
                "Preview is currently only supported for image files.\n\n"
                "Use 'Open Attachment' to view other file types."
            )
            return
        
        # Show progress cursor
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        
        try:
            # Get temp path (runs on main thread - required for COM)
            temp_path = self.outlook.get_attachment_preview_path(attach['email_id'], attach['attachment_index'])
            
            QApplication.restoreOverrideCursor()
            
            if temp_path and os.path.exists(temp_path):
                dialog = ImagePreviewDialog(temp_path, self)
                dialog.exec()
            else:
                QMessageBox.warning(self, "Error", "Failed to load preview")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Error", f"Failed to load preview: {e}")
    
    def copy_selected_to_downloads(self):
        """Copy selected attachments to Downloads folder"""
        logger.debug("copy_selected_to_downloads called")
        selected = self.get_selected_attachments()
        
        if not selected:
            logger.warning("No attachments selected for download")
            QMessageBox.warning(self, "No Selection", "Please select attachments to copy")
            return
        
        logger.info(f"Attempting to download {len(selected)} attachment(s)")
        # Get Downloads folder
        downloads_folder = str(Path.home() / "Downloads")
        
        # Verify Downloads folder exists
        if not os.path.exists(downloads_folder):
            os.makedirs(downloads_folder, exist_ok=True)
        
        # Confirm
        reply = QMessageBox.question(
            self,
            "Copy Attachments",
            f"Copy {len(selected)} attachment(s) to:\n{downloads_folder}\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Copy attachments
        success_count = 0
        failed = []
        saved_files = []
        
        for attach in selected:
            save_path = os.path.join(downloads_folder, attach['attachment_name'])
            success = self.outlook.save_attachment(attach['email_id'], attach['attachment_index'], save_path)
            
            if success:
                success_count += 1
                # Check what file was actually created (might have different name due to conflicts)
                if os.path.exists(save_path):
                    saved_files.append(save_path)
                else:
                    # File was renamed due to conflict - find it
                    base, ext = os.path.splitext(save_path)
                    counter = 1
                    while os.path.exists(f"{base}_{counter}{ext}"):
                        saved_files.append(f"{base}_{counter}{ext}")
                        counter += 1
                        break
            else:
                failed.append(attach['attachment_name'])
        
        # Show result with actual paths
        if failed:
            QMessageBox.warning(
                self, "Partial Success",
                f"Copied {success_count} of {len(selected)} attachments.\n\n"
                f"Failed: {', '.join(failed)}"
            )
        else:
            msg = f"Successfully copied {success_count} attachment(s) to Downloads folder:\n{downloads_folder}"
            if saved_files:
                msg += f"\n\nFiles saved:\n" + "\n".join([os.path.basename(f) for f in saved_files[:5]])
                if len(saved_files) > 5:
                    msg += f"\n... and {len(saved_files) - 5} more"
            
            QMessageBox.information(self, "Success", msg)
    
    def open_downloads_folder(self):
        """Open the Downloads folder in File Navigator"""
        downloads_folder = str(Path.home() / "Downloads")
        
        # Ensure Downloads folder exists
        if not os.path.exists(downloads_folder):
            os.makedirs(downloads_folder, exist_ok=True)
        
        # Open in File Navigator
        if self.launcher and hasattr(self.launcher, 'file_nav_window'):
            # Ensure File Navigator is open
            if self.launcher.file_nav_window is None:
                self.launcher.open_file_navigator()
            
            # Show the window
            self.launcher.file_nav_window.show()
            self.launcher.file_nav_window.raise_()
            self.launcher.file_nav_window.activateWindow()
            
            # Navigate to Downloads folder
            if hasattr(self.launcher.file_nav_window, 'navigate_to_bookmark_folder'):
                self.launcher.file_nav_window.navigate_to_bookmark_folder(downloads_folder)
        else:
            # Fallback to Windows Explorer if no launcher reference
            try:
                os.startfile(downloads_folder)
            except Exception as e:
                QMessageBox.warning(
                    self, "Error",
                    f"Could not open Downloads folder:\n{e}"
                )
    
    def archive_selected_attachments(self):
        """Archive selected attachments to a chosen directory"""
        selected = self.get_selected_attachments()
        
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select attachments to archive")
            return
        
        # Choose directory
        archive_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Archive Directory",
            str(Path.home()),
            QFileDialog.Option.ShowDirsOnly
        )
        
        if not archive_dir:
            return
        
        # Create archive with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = os.path.join(archive_dir, f"Email_Attachments_{timestamp}")
        os.makedirs(archive_path, exist_ok=True)
        
        # Copy attachments
        success_count = 0
        manifest = []
        
        for attach in selected:
            save_path = os.path.join(archive_path, attach['attachment_name'])
            success = self.outlook.save_attachment(attach['email_id'], attach['attachment_index'], save_path)
            
            if success:
                success_count += 1
                manifest.append({
                    'file': attach['attachment_name'],
                    'email_subject': attach['email_subject'],
                    'sender': attach['email_sender'],
                    'date': attach['email_date']
                })
        
        # Create manifest file
        if manifest:
            manifest_path = os.path.join(archive_path, "_MANIFEST.txt")
            with open(manifest_path, 'w', encoding='utf-8') as f:
                f.write("Email Attachments Archive\n")
                f.write(f"Created: {datetime.now()}\n")
                f.write(f"Total Files: {len(manifest)}\n\n")
                
                for item in manifest:
                    f.write(f"File: {item['file']}\n")
                    f.write(f"  Email: {item['email_subject']}\n")
                    f.write(f"  From: {item['sender']}\n")
                    f.write(f"  Date: {item['date']}\n\n")
        
        QMessageBox.information(
            self, "Archive Complete",
            f"Archived {success_count} attachment(s) to:\n{archive_path}"
        )
    
    def get_selected_attachments(self) -> List[Dict]:
        """Get currently selected attachments from selected cells or rows"""
        if not hasattr(self, 'attachment_data') or self.attachment_data.empty:
            logger.warning("No attachment data available")
            return []
        
        # Get selected indexes (can be cells or rows)
        selected_indexes = self.attachments_grid.table_view.selectionModel().selectedIndexes()
        
        if not selected_indexes:
            logger.debug("No cells/rows selected")
            return []
        
        # Extract unique row numbers from selected indexes
        selected_row_nums = set(index.row() for index in selected_indexes)
        logger.debug(f"Selected rows (filtered view): {selected_row_nums}")
        
        # Map filtered view rows to original data rows
        attachments = []
        if hasattr(self.attachments_grid, 'model') and self.attachments_grid.model:
            display_indices = self.attachments_grid.model._display_indices
            for row in sorted(selected_row_nums):
                if row >= 0 and row < len(display_indices):
                    actual_index = display_indices[row]
                    attach_dict = self.attachment_data.loc[actual_index].to_dict()
                    attachments.append(attach_dict)
        else:
            # Fallback if no filtering is active
            for row in sorted(selected_row_nums):
                if row >= 0 and row < len(self.attachment_data):
                    attach_dict = self.attachment_data.iloc[row].to_dict()
                    attachments.append(attach_dict)
        
        logger.info(f"Found {len(attachments)} selected attachments")
        return attachments

