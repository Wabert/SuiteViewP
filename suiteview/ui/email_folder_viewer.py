"""
Email Folder Viewer - View and search emails from a specific folder
"""

import logging
import pandas as pd
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from suiteview.data.repositories import get_email_repository
from suiteview.core.outlook_manager import get_outlook_manager
from suiteview.ui.components.filter_table_view import FilterTableView

logger = logging.getLogger(__name__)


class EmailFolderViewer(QWidget):
    """Viewer for emails in a specific folder with search/filter"""
    
    def __init__(self, folder_path: str, folder_name: str):
        super().__init__()
        self.folder_path = folder_path
        self.folder_name = folder_name
        
        self.setWindowTitle(f"Email Folder: {folder_name}")
        self.resize(1200, 700)
        
        self.init_ui()
        self.load_data()
    
    def init_ui(self):
        """Initialize UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Title
        title = QLabel(f"📁 {self.folder_name}")
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Info label
        self.info_label = QLabel("Loading emails...")
        self.info_label.setStyleSheet("color: #666;")
        layout.addWidget(self.info_label)
        
        # Button row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setMinimumHeight(30)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 15px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        refresh_btn.clicked.connect(self.load_data)
        btn_layout.addWidget(refresh_btn)
        
        # Open in Outlook button
        open_btn = QPushButton("📧 Open in Outlook")
        open_btn.setMinimumHeight(30)
        open_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 15px;
            }
            QPushButton:hover { background-color: #0b7dda; }
        """)
        open_btn.clicked.connect(self.open_selected_email)
        btn_layout.addWidget(open_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # Email table
        self.table_view = FilterTableView()
        layout.addWidget(self.table_view, 1)
        
        # Double-click to open email
        self.table_view.table.doubleClicked.connect(self.on_email_double_click)
    
    def load_data(self):
        """Load emails from database"""
        try:
            repo = get_email_repository()
            emails = repo.get_all_emails(folder_path=self.folder_path)
            
            if not emails:
                self.info_label.setText("No emails found in this folder")
                return
            
            # Convert to DataFrame
            df = pd.DataFrame(emails)
            
            # Parse dates
            df['received_date'] = pd.to_datetime(df['received_date'], format='ISO8601')
            
            # Reorder and rename columns
            display_df = df[['subject', 'sender', 'sender_email', 'received_date', 
                           'size', 'unread', 'has_attachments', 'attachment_count']]
            
            display_df.columns = ['Subject', 'Sender', 'Email', 'Date', 
                                 'Size (bytes)', 'Unread', 'Has Attachments', 'Attachment Count']
            
            # Load into table
            self.table_view.load_data(display_df)
            
            # Store original data for row lookups
            self.emails_data = emails
            
            # Update info
            unread_count = df['unread'].sum()
            self.info_label.setText(
                f"{len(emails)} emails | {unread_count} unread | "
                f"{df['has_attachments'].sum()} with attachments"
            )
        
        except Exception as e:
            logger.error(f"Error loading folder emails: {e}", exc_info=True)
            self.info_label.setText(f"Error: {str(e)}")
    
    def on_email_double_click(self, index):
        """Handle double-click on email row"""
        row = index.row()
        
        if row < 0 or row >= len(self.emails_data):
            return
        
        email = self.emails_data[row]
        self.open_email(email['email_id'])
    
    def open_selected_email(self):
        """Open selected email in Outlook"""
        selected = self.table_view.table.selectionModel().selectedRows()
        
        if not selected:
            return
        
        row = selected[0].row()
        if row < 0 or row >= len(self.emails_data):
            return
        
        email = self.emails_data[row]
        self.open_email(email['email_id'])
    
    def open_email(self, email_id: str):
        """Open email in Outlook by ID"""
        outlook = get_outlook_manager()
        outlook.open_email(email_id)
