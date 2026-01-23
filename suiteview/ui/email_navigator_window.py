"""
Email Navigator - Main launcher window for email management features

Provides access to:
- Email Browser (browse and search emails)
- Attachment Manager (find and manage email attachments)
- Future email management tools
"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QMessageBox, QProgressDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from suiteview.core.outlook_manager import get_outlook_manager
from suiteview.data.repositories import get_email_repository

logger = logging.getLogger(__name__)


class EmailSyncThread(QThread):
    """Background thread for syncing emails from Outlook"""
    progress = pyqtSignal(str, int, int)  # message, current, total
    finished = pyqtSignal(bool, str)  # success, message
    
    def __init__(self, sync_attachments=False, full_sync=False, folder_path=None, max_limit=1000):
        super().__init__()
        self.sync_attachments = sync_attachments
        self.full_sync = full_sync  # True = rescan all, False = incremental
        self.folder_path = folder_path  # Specific folder path, or None for Inbox
        self.max_limit = max_limit
    
    def run(self):
        """Run email sync"""
        thread_db = None
        outlook = None
        try:
            logger.info("=== EMAIL SYNC STARTED ===")
            logger.info(f"Full sync: {self.full_sync}, Max limit: {self.max_limit}")
            
            # Import here to ensure COM and DB are initialized in this thread
            from suiteview.core.outlook_manager import OutlookManager
            from suiteview.data.repositories import EmailRepository
            from suiteview.data.database import Database
            
            # Create fresh instances in this thread
            # (COM and SQLite objects can't cross thread boundaries)
            logger.info("Creating OutlookManager instance...")
            outlook = OutlookManager()
            
            # Create thread-local database connection
            logger.info("Creating thread-local database connection...")
            thread_db = Database()
            thread_db.connect()
            
            # Create repository with thread-local database
            logger.info("Creating EmailRepository...")
            repo = EmailRepository(db=thread_db)
            logger.info("EmailRepository created successfully")
            
            if not outlook.is_connected():
                logger.error("Outlook not connected")
                self.finished.emit(False, "Could not connect to Outlook")
                return
            
            # Get target folder
            if self.folder_path:
                logger.info(f"Getting folder: {self.folder_path}")
                self.progress.emit(f"Getting folder {self.folder_path}...", 0, 100)
                folder = outlook.get_folder_by_path(self.folder_path)
                folder_name = self.folder_path.split('/')[-1]
            else:
                logger.info("Getting Inbox folder...")
                self.progress.emit("Getting Inbox folder...", 0, 100)
                folder = outlook.get_inbox_folder()
                folder_name = "Inbox"
            
            if not folder:
                logger.error(f"Could not access folder: {folder_name}")
                self.finished.emit(False, f"Could not access folder: {folder_name}")
                return
            
            # Clear database if doing full sync
            if self.full_sync:
                logger.info("Full sync - clearing old data...")
                self.progress.emit("Clearing old data for full sync...", 10, 100)
                try:
                    repo.clear_cache(folder_path=None)  # Clear Inbox data
                    logger.info("Cleared existing email cache for full sync")
                except Exception as e:
                    logger.error(f"Error clearing cache: {e}", exc_info=True)
                    self.finished.emit(False, f"Error clearing cache: {str(e)}")
                    return
            
            # Determine sync strategy
            if self.full_sync:
                logger.info(f"Full sync: Loading up to {self.max_limit} emails from {folder_name}...")
                self.progress.emit(f"Full sync: Loading all emails from {folder_name}...", 20, 100)
                emails = outlook.get_emails(folder, limit=self.max_limit, include_body_preview=False)
            else:
                # Incremental sync - only get emails since last sync
                last_sync = repo.get_last_sync_time()
                if last_sync:
                    logger.info(f"Incremental sync: Loading emails since {last_sync}...")
                    self.progress.emit(f"Incremental sync: Loading emails since {last_sync.strftime('%m/%d/%Y %H:%M')}...", 20, 100)
                    emails = outlook.get_emails_since(folder, since_date=last_sync, include_body_preview=False)
                else:
                    logger.info("No previous sync found - doing full sync...")
                    self.progress.emit("No previous sync found - doing full sync...", 20, 100)
                    emails = outlook.get_emails(folder, limit=self.max_limit, include_body_preview=False)
            
            logger.info(f"Retrieved {len(emails)} emails")
            
            if not emails:
                logger.warning("No emails found")
                self.finished.emit(True, "No emails found in Inbox")
                return
            
            # Save to cache
            logger.info(f"Saving {len(emails)} emails to database...")
            self.progress.emit(f"Caching {len(emails)} emails...", 50, 100)
            
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
            
            repo.save_emails(email_dicts)
            
            # Sync attachments if requested
            attachment_count = 0
            if self.sync_attachments:
                if self.full_sync:
                    self.progress.emit("Full sync: Scanning all attachments...", 70, 100)
                    attachments = outlook.get_all_attachments([folder], limit_per_folder=self.max_limit, calculate_hash=True)
                else:
                    # Only scan attachments from the new emails we just retrieved
                    self.progress.emit(f"Scanning attachments from {len(emails)} new emails...", 70, 100)
                    attachments = outlook.get_attachments_from_emails(emails, calculate_hash=True)
                
                if attachments:
                    self.progress.emit(f"Caching {len(attachments)} attachments...", 85, 100)
                    
                    # Convert EmailAttachment objects to dicts
                    attach_dicts = []
                    for attach in attachments:
                        attach_dicts.append({
                            'email_id': attach.email_id,
                            'email_subject': attach.email_subject,
                            'email_sender': attach.email_sender,
                            'email_date': attach.email_date,
                            'attachment_name': attach.attachment_name,
                            'attachment_type': attach.attachment_type,
                            'attachment_size': attach.attachment_size,
                            'attachment_index': attach.attachment_index,
                            'file_hash': attach.file_hash
                        })
                    
                    repo.save_attachments(attach_dicts)
                    attachment_count = len(attachments)
            
            # Update sync status
            repo.update_sync_status(folder_name, len(emails), attachment_count, scan_complete=True)
            
            # Record sync time for incremental syncs
            repo.record_sync_time()
            
            self.progress.emit("Sync complete!", 100, 100)
            
            msg = f"Successfully synced {len(emails)} emails"
            if self.sync_attachments:
                msg += f" and {attachment_count} attachments"
            
            self.finished.emit(True, msg)
        
        except Exception as e:
            logger.error(f"Error during email sync: {e}", exc_info=True)
            self.finished.emit(False, f"Error: {str(e)}")
        
        finally:
            # Clean up resources
            try:
                if thread_db:
                    logger.info("Closing thread database connection...")
                    thread_db.close()
                if outlook:
                    logger.info("Cleaning up Outlook connection...")
                    outlook.cleanup()
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")


class EmailNavigatorWindow(QWidget):
    """Main Email Navigator launcher window"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Window references (separate windows launched from here)
        self.attachment_manager_window = None
        self.email_browser_window = None
        self.sync_thread = None
        self.progress_dialog = None
        
        self.init_ui()
        
        # Check Outlook connection
        self.check_outlook_connection()
    
    def init_ui(self):
        """Initialize UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(8)
        
        # Title
        title = QLabel("📧 Email Navigator")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Connection status
        self.status_label = QLabel("Checking Outlook connection...")
        self.status_label.setStyleSheet("color: #666;")
        layout.addWidget(self.status_label)
        
        # Sync info (move to top)
        self.sync_info_label = QLabel("No sync performed yet")
        self.sync_info_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self.sync_info_label)
        
        # Control buttons row
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)
        
        # Max emails input
        limit_label = QLabel("Max:")
        limit_label.setStyleSheet("font-size: 11px;")
        controls_layout.addWidget(limit_label)
        
        from PyQt6.QtWidgets import QLineEdit
        self.max_limit_input = QLineEdit()
        self.max_limit_input.setText("1000")
        self.max_limit_input.setFixedWidth(60)
        self.max_limit_input.setStyleSheet("padding: 2px; font-size: 11px;")
        self.max_limit_input.setToolTip("Maximum number of emails to sync")
        controls_layout.addWidget(self.max_limit_input)
        
        controls_layout.addStretch()
        
        # Sync Update button
        self.sync_update_btn = QPushButton("⬆️ Sync Update")
        self.sync_update_btn.setMinimumHeight(35)
        self.sync_update_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        self.sync_update_btn.setToolTip("Add new emails/attachments since last sync")
        self.sync_update_btn.clicked.connect(self.sync_update)
        controls_layout.addWidget(self.sync_update_btn)
        
        # Sync All button
        self.sync_all_btn = QPushButton("🔄 Sync All")
        self.sync_all_btn.setMinimumHeight(35)
        self.sync_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #0b7dda; }
        """)
        self.sync_all_btn.setToolTip("Full rescan of all emails/attachments")
        self.sync_all_btn.clicked.connect(self.sync_all)
        controls_layout.addWidget(self.sync_all_btn)
        
        # View Attachments button
        self.view_btn = QPushButton("📎 View Attachments")
        self.view_btn.setMinimumHeight(35)
        self.view_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #e68900; }
        """)
        self.view_btn.setToolTip("View and search email attachments")
        self.view_btn.clicked.connect(self.view_attachments)
        controls_layout.addWidget(self.view_btn)
        
        layout.addLayout(controls_layout)
        
        # Stretch to push everything to top
        layout.addStretch()
        
        # Update sync info on load
        self.update_sync_info()
    
    def sync_update(self):
        """Incremental sync - only add new emails/attachments"""
        self.start_sync(full_sync=False)
    
    def sync_all(self):
        """Full sync - rescan all emails/attachments and overwrite database"""
        reply = QMessageBox.question(
            self,
            "Full Sync",
            "This will rescan ALL emails and attachments from Inbox.\\n"
            "This can take several minutes.\\n\\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.start_sync(full_sync=True)
    
    def start_sync(self, full_sync: bool):
        """Start email sync in background thread"""
        try:
            max_limit = int(self.max_limit_input.text())
        except ValueError:
            max_limit = 1000
        
        # Disable buttons
        self.sync_update_btn.setEnabled(False)
        self.sync_all_btn.setEnabled(False)
        self.view_btn.setEnabled(False)
        
        # Create progress dialog
        sync_type = "Full Sync" if full_sync else "Incremental Sync"
        self.progress_dialog = QProgressDialog(f"Initializing {sync_type}...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.canceled.connect(self.cancel_sync)
        
        # Clean up old thread if exists
        if self.sync_thread is not None:
            if self.sync_thread.isRunning():
                self.sync_thread.terminate()
                self.sync_thread.wait()
            self.sync_thread.deleteLater()
            self.sync_thread = None
        
        # Create and start sync thread
        self.sync_thread = EmailSyncThread(
            sync_attachments=True,
            full_sync=full_sync,
            folder_path=None,  # None = Inbox
            max_limit=max_limit
        )
        self.sync_thread.progress.connect(self.on_sync_progress)
        self.sync_thread.finished.connect(self.on_sync_finished)
        self.sync_thread.start()
    
    def view_attachments(self):
        """Open attachment manager"""
        self.open_attachment_manager()
    
    def check_outlook_connection(self):
        """Check if Outlook is connected"""
        outlook = get_outlook_manager()
        
        if outlook.is_connected():
            self.status_label.setText("✅ Connected to Outlook")
            self.status_label.setStyleSheet("color: green; padding: 5px;")
        else:
            self.status_label.setText("❌ Not connected to Outlook. Install pywin32 and ensure Outlook is available.")
            self.status_label.setStyleSheet("color: red; padding: 5px;")
    
    def update_sync_info(self):
        """Update sync status information"""
        repo = get_email_repository()
        status = repo.get_sync_status("Inbox")
        
        if status:
            info = status[0]
            self.sync_info_label.setText(
                f"Last sync: {info['last_sync_time']} | "
                f"{info['email_count']} emails | "
                f"{info['attachment_count']} attachments"
            )
        else:
            self.sync_info_label.setText("No sync performed yet")
    

    
    def on_sync_progress(self, message: str, current: int, total: int):
        """Handle sync progress updates"""
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.setLabelText(message)
            self.progress_dialog.setValue(current)
    
    def on_sync_finished(self, success: bool, message: str):
        """Handle sync completion"""
        try:
            # Close progress dialog
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.close()
                self.progress_dialog = None
            
            # Re-enable buttons
            self.sync_update_btn.setEnabled(True)
            self.sync_all_btn.setEnabled(True)
            self.view_btn.setEnabled(True)
            
            # Show result
            if success:
                QMessageBox.information(self, "Sync Complete", message)
                self.update_sync_info()
            else:
                QMessageBox.warning(self, "Sync Failed", message)
        
        except Exception as e:
            logger.error(f"Error in on_sync_finished: {e}", exc_info=True)
            # Make sure buttons are re-enabled even if there's an error
            self.sync_update_btn.setEnabled(True)
            self.sync_all_btn.setEnabled(True)
            self.view_btn.setEnabled(True)
    
    def cancel_sync(self):
        """Cancel ongoing sync"""
        if hasattr(self, 'sync_thread') and self.sync_thread:
            self.sync_thread.terminate()
            self.sync_update_btn.setEnabled(True)
            self.sync_all_btn.setEnabled(True)
            self.view_btn.setEnabled(True)
    
    def open_attachment_manager(self):
        """Open Attachment Manager window"""
        if self.attachment_manager_window is None:
            from suiteview.ui.email_attachment_manager import EmailAttachmentManager
            # Pass launcher reference if available
            launcher = getattr(self, 'launcher', None)
            self.attachment_manager_window = EmailAttachmentManager(launcher=launcher)
            
            # Override close to hide instead of destroy
            def hide_on_close(event):
                event.ignore()
                self.attachment_manager_window.hide()
            
            self.attachment_manager_window.closeEvent = hide_on_close
        
        self.attachment_manager_window.show()
        self.attachment_manager_window.activateWindow()
    
    def open_email_browser(self):
        """Open Email Browser window"""
        if self.email_browser_window is None:
            from suiteview.ui.email_browser_window import EmailBrowserWindow
            self.email_browser_window = EmailBrowserWindow()
            
            # Override close to hide instead of destroy
            def hide_on_close(event):
                event.ignore()
                self.email_browser_window.hide()
            
            self.email_browser_window.closeEvent = hide_on_close
        
        self.email_browser_window.show()
        self.email_browser_window.activateWindow()
