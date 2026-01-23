"""
Email Browser Window - Browse and search emails with folder navigation

Features:
- 3-panel layout: Folders | Email List | Preview
- Folder tree navigation
- Filterable email list using FilterTableView
- Email preview pane with HTML support
- Mark as read/unread
- Basic email actions
"""

import logging
from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSplitter, QTreeWidget, QTreeWidgetItem, QTextEdit, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

import pandas as pd

from suiteview.ui.widgets.filter_table_view import FilterTableView
from suiteview.core.outlook_manager import get_outlook_manager
from suiteview.data.repositories import get_email_repository

logger = logging.getLogger(__name__)


class EmailBrowserWindow(QWidget):
    """Email Browser with folder navigation and preview"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.outlook = get_outlook_manager()
        self.repo = get_email_repository()
        
        self.current_folder_path = None
        self.emails_data = pd.DataFrame()
        
        self.setWindowTitle("SuiteView - Email Browser")
        self.resize(1400, 800)
        
        self.init_ui()
        self.load_folders()
        self.load_emails()
    
    def init_ui(self):
        """Initialize UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Title bar
        title_layout = QHBoxLayout()
        
        title = QLabel("📬 Email Browser")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title_layout.addWidget(title)
        
        title_layout.addStretch()
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setFixedHeight(30)
        refresh_btn.clicked.connect(self.refresh_current_folder)
        title_layout.addWidget(refresh_btn)
        
        layout.addLayout(title_layout)
        
        # Main splitter (3 panels)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel - Folders
        folders_panel = self.create_folders_panel()
        main_splitter.addWidget(folders_panel)
        
        # Middle panel - Email list
        emails_panel = self.create_emails_panel()
        main_splitter.addWidget(emails_panel)
        
        # Right panel - Preview
        preview_panel = self.create_preview_panel()
        main_splitter.addWidget(preview_panel)
        
        # Set initial sizes
        main_splitter.setSizes([250, 600, 550])
        
        layout.addWidget(main_splitter)
        
        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #666; padding: 3px;")
        layout.addWidget(self.status_label)
    
    def create_folders_panel(self):
        """Create folders tree panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        
        # Title
        label = QLabel("📁 Folders")
        label_font = QFont()
        label_font.setBold(True)
        label.setFont(label_font)
        layout.addWidget(label)
        
        # Folder tree
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderLabel("Email Folders")
        self.folder_tree.itemClicked.connect(self.on_folder_selected)
        layout.addWidget(self.folder_tree)
        
        return panel
    
    def create_emails_panel(self):
        """Create email list panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        
        # Toolbar
        toolbar = QHBoxLayout()
        
        self.open_email_btn = QPushButton("📧 Open in Outlook")
        self.open_email_btn.setFixedHeight(28)
        self.open_email_btn.clicked.connect(self.open_selected_email)
        toolbar.addWidget(self.open_email_btn)
        
        self.mark_read_btn = QPushButton("✓ Mark Read")
        self.mark_read_btn.setFixedHeight(28)
        self.mark_read_btn.clicked.connect(self.mark_selected_as_read)
        toolbar.addWidget(self.mark_read_btn)
        
        self.mark_unread_btn = QPushButton("✗ Mark Unread")
        self.mark_unread_btn.setFixedHeight(28)
        self.mark_unread_btn.clicked.connect(self.mark_selected_as_unread)
        toolbar.addWidget(self.mark_unread_btn)
        
        toolbar.addStretch()
        
        # Unread filter checkbox
        from PyQt6.QtWidgets import QCheckBox
        self.unread_only_check = QCheckBox("Unread Only")
        self.unread_only_check.stateChanged.connect(self.load_emails)
        toolbar.addWidget(self.unread_only_check)
        
        layout.addLayout(toolbar)
        
        # Email grid
        self.emails_grid = FilterTableView()
        layout.addWidget(self.emails_grid)
        
        # Connect selection changed
        if hasattr(self.emails_grid, 'table_view'):
            self.emails_grid.table_view.selectionModel().selectionChanged.connect(
                self.on_email_selection_changed
            )
            self.emails_grid.table_view.doubleClicked.connect(self.on_email_double_click)
        
        return panel
    
    def create_preview_panel(self):
        """Create email preview panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        
        # Title
        label = QLabel("📄 Preview")
        label_font = QFont()
        label_font.setBold(True)
        label.setFont(label_font)
        layout.addWidget(label)
        
        # Email details
        self.preview_header = QLabel("(No email selected)")
        self.preview_header.setWordWrap(True)
        self.preview_header.setStyleSheet("""
            background-color: #f0f0f0;
            padding: 8px;
            border: 1px solid #ccc;
            border-radius: 3px;
        """)
        layout.addWidget(self.preview_header)
        
        # Email body preview
        self.preview_body = QTextEdit()
        self.preview_body.setReadOnly(True)
        layout.addWidget(self.preview_body)
        
        return panel
    
    def load_folders(self):
        """Load folder tree from Outlook"""
        if not self.outlook.is_connected():
            self.status_label.setText("Not connected to Outlook")
            return
        
        self.folder_tree.clear()
        
        try:
            folders = self.outlook.get_folder_tree()
            
            for store in folders:
                store_item = QTreeWidgetItem(self.folder_tree, [store['name']])
                store_item.setData(0, Qt.ItemDataRole.UserRole, store['path'])
                
                self._add_folder_items(store_item, store.get('children', []))
            
            self.folder_tree.expandAll()
        
        except Exception as e:
            logger.error(f"Error loading folders: {e}")
            self.status_label.setText(f"Error loading folders: {e}")
    
    def _add_folder_items(self, parent_item: QTreeWidgetItem, folders: List[Dict]):
        """Recursively add folder items to tree"""
        for folder in folders:
            # Show item count in name
            name = f"{folder['name']} ({folder.get('item_count', 0)})"
            if folder.get('unread_count', 0) > 0:
                name += f" [{folder['unread_count']} unread]"
            
            item = QTreeWidgetItem(parent_item, [name])
            item.setData(0, Qt.ItemDataRole.UserRole, folder['path'])
            
            if folder.get('children'):
                self._add_folder_items(item, folder['children'])
    
    def on_folder_selected(self, item: QTreeWidgetItem, column: int):
        """Handle folder selection"""
        folder_path = item.data(0, Qt.ItemDataRole.UserRole)
        
        if folder_path != self.current_folder_path:
            self.current_folder_path = folder_path
            self.load_emails()
    
    def load_emails(self):
        """Load emails for current folder"""
        # Load from cache first
        unread_only = self.unread_only_check.isChecked() if hasattr(self, 'unread_only_check') else False
        
        emails = self.repo.get_all_emails(
            folder_path=self.current_folder_path,
            unread_only=unread_only
        )
        
        if not emails:
            self.status_label.setText("No emails found. Try syncing from Email Navigator.")
            self.emails_grid.set_dataframe(pd.DataFrame())
            return
        
        # Convert to DataFrame
        df = pd.DataFrame(emails)
        
        # Format date
        df['date'] = pd.to_datetime(df['received_date']).dt.strftime('%Y-%m-%d %H:%M')
        
        # Format size
        df['size_kb'] = df['size'].apply(lambda x: f"{x / 1024:.1f}")
        
        # Unread indicator
        df['unread_flag'] = df['unread'].apply(lambda x: '✉️' if x else '')
        
        # Select columns for display - use sender_email instead of sender for From column
        display_df = df[[
            'unread_flag', 'subject', 'sender_email', 'date', 'size_kb', 'attachment_count'
        ]].copy()
        
        display_df.columns = [
            '', 'Subject', 'From', 'Date', 'Size (KB)', 'Attachments'
        ]
        
        # Store original data
        self.emails_data = df
        
        # Load into grid
        self.emails_grid.set_dataframe(display_df)
        
        self.status_label.setText(f"Loaded {len(emails)} emails from {self.current_folder_path or 'cache'}")
    
    def on_email_selection_changed(self):
        """Handle email selection change"""
        selected = self.get_selected_emails()
        
        if not selected:
            self.preview_header.setText("(No email selected)")
            self.preview_body.clear()
            return
        
        # Show first selected email
        email = selected[0]
        
        # Update header
        header_html = f"""
        <b>From:</b> {email['sender']} ({email['sender_email']})<br>
        <b>Subject:</b> {email['subject']}<br>
        <b>Date:</b> {email['received_date']}<br>
        <b>Size:</b> {email['size'] / 1024:.1f} KB<br>
        <b>Attachments:</b> {email['attachment_count']}
        """
        self.preview_header.setText(header_html)
        
        # Update body preview
        body_text = email.get('body_preview', '(No preview available)')
        self.preview_body.setPlainText(body_text)
    
    def on_email_double_click(self, index):
        """Handle double-click on email"""
        self.open_selected_email()
    
    def open_selected_email(self):
        """Open selected email in Outlook"""
        selected = self.get_selected_emails()
        
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select an email first")
            return
        
        if not self.outlook.is_connected():
            QMessageBox.warning(self, "Outlook Error", "Not connected to Outlook")
            return
        
        # Open first selected email
        email = selected[0]
        success = self.outlook.open_email(email['email_id'])
        
        if not success:
            QMessageBox.warning(self, "Error", "Failed to open email")
    
    def mark_selected_as_read(self):
        """Mark selected emails as read"""
        selected = self.get_selected_emails()
        
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select email(s) to mark as read")
            return
        
        if not self.outlook.is_connected():
            QMessageBox.warning(self, "Outlook Error", "Not connected to Outlook")
            return
        
        success_count = 0
        for email in selected:
            if self.outlook.mark_as_read(email['email_id']):
                success_count += 1
        
        QMessageBox.information(
            self, "Success",
            f"Marked {success_count} of {len(selected)} email(s) as read"
        )
        
        # Refresh view
        self.refresh_current_folder()
    
    def mark_selected_as_unread(self):
        """Mark selected emails as unread"""
        selected = self.get_selected_emails()
        
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select email(s) to mark as unread")
            return
        
        if not self.outlook.is_connected():
            QMessageBox.warning(self, "Outlook Error", "Not connected to Outlook")
            return
        
        success_count = 0
        for email in selected:
            if self.outlook.mark_as_unread(email['email_id']):
                success_count += 1
        
        QMessageBox.information(
            self, "Success",
            f"Marked {success_count} of {len(selected)} email(s) as unread"
        )
        
        # Refresh view
        self.refresh_current_folder()
    
    def refresh_current_folder(self):
        """Refresh current folder from Outlook"""
        if not self.outlook.is_connected():
            QMessageBox.warning(self, "Outlook Error", "Not connected to Outlook")
            return
        
        if not self.current_folder_path:
            QMessageBox.information(
                self, "No Folder Selected",
                "Please select a folder first, or run a full sync from Email Navigator"
            )
            return
        
        # Get folder from Outlook
        folder = self.outlook.get_folder_by_path(self.current_folder_path)
        
        if not folder:
            QMessageBox.warning(self, "Error", f"Could not find folder: {self.current_folder_path}")
            return
        
        # Load emails
        self.status_label.setText("Loading emails from Outlook...")
        
        emails = self.outlook.get_emails(folder, limit=1000, include_body_preview=True)
        
        if emails:
            # Convert EmailInfo objects to dicts
            email_dicts = []
            for email in emails:
                email_dicts.append({
                    'email_id': email.email_id,
                    'subject': email.subject,
                    'sender': email.sender,
                    'sender_email': email.sender_email,
                    'received_date': email.received_date,
                    'size': email.size,
                    'unread': email.unread,
                    'has_attachments': email.has_attachments,
                    'attachment_count': email.attachment_count,
                    'folder_path': email.folder_path,
                    'body_preview': email.body_preview
                })
            
            # Update cache
            self.repo.save_emails(email_dicts)
        
        # Reload view
        self.load_emails()
    
    def get_selected_emails(self) -> List[Dict]:
        """Get currently selected emails"""
        if self.emails_data.empty:
            return []
        
        selected_rows = self.emails_grid.table_view.selectionModel().selectedRows()
        
        emails = []
        for index in selected_rows:
            # Map to source model
            source_index = self.emails_grid.table_view.model().mapToSource(index)
            row = source_index.row()
            
            if row >= 0 and row < len(self.emails_data):
                email_dict = self.emails_data.iloc[row].to_dict()
                emails.append(email_dict)
        
        return emails
