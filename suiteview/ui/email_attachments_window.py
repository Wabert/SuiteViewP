"""
Email Attachments Window - Simple view of recent email attachments

Features:
- Shows Sender Name, Sent Date, Attachment Name
- Configurable scan period with persistence
- Caches attachments in database for faster subsequent loads
- Filterable columns using FilterTableView
- Double-click on attachment name to open attachment
- Double-click on sender/date to open email
- Modeless, movable, resizable window
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QMessageBox, QApplication, QSizeGrip, QComboBox, QFileIconProvider,
    QStyledItemDelegate, QStyle
)
from PyQt6.QtCore import Qt, QPoint, QTimer, QThread, pyqtSignal, QFileInfo, QSize
from PyQt6.QtGui import QFont, QPainter, QColor, QBrush, QPixmap, QIcon

from suiteview.ui.widgets.filter_table_view import FilterTableView
from suiteview.core.outlook_manager import get_outlook_manager
from suiteview.data.repositories import get_email_repository

logger = logging.getLogger(__name__)

# Shared icon provider for file icons
_icon_provider = None
_icon_cache = {}

def get_file_icon(filename: str) -> QIcon:
    """Get the system icon for a file based on its extension"""
    global _icon_provider, _icon_cache
    
    if _icon_provider is None:
        _icon_provider = QFileIconProvider()
    
    # Get extension
    ext = os.path.splitext(filename)[1].lower() if filename else ''
    
    # Check cache
    if ext in _icon_cache:
        return _icon_cache[ext]
    
    # Create a temporary QFileInfo to get the icon
    # Use extension-based lookup
    if ext:
        file_info = QFileInfo(f"temp{ext}")
        icon = _icon_provider.icon(file_info)
    else:
        icon = _icon_provider.icon(QFileIconProvider.IconType.File)
    
    _icon_cache[ext] = icon
    return icon


class FileIconDelegate(QStyledItemDelegate):
    """Delegate that shows file icons next to filenames"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.icon_size = 16
    
    def paint(self, painter, option, index):
        # Get the filename
        filename = index.data(Qt.ItemDataRole.DisplayRole)
        if not filename:
            super().paint(painter, option, index)
            return
        
        # Draw selection background if selected
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        
        # Get the icon
        icon = get_file_icon(filename)
        
        # Calculate positions
        icon_rect = option.rect.adjusted(2, (option.rect.height() - self.icon_size) // 2, 0, 0)
        icon_rect.setWidth(self.icon_size)
        icon_rect.setHeight(self.icon_size)
        
        text_rect = option.rect.adjusted(self.icon_size + 6, 0, 0, 0)
        
        # Draw icon
        icon.paint(painter, icon_rect)
        
        # Draw text
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(option.palette.text().color())
        
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, filename)
    
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        # Add space for icon
        size.setWidth(size.width() + self.icon_size + 6)
        return size


# Scan period options: (display text, days)
SCAN_PERIODS = [
    ("3 Days", 3),
    ("1 Week", 7),
    ("2 Weeks", 14),
    ("3 Weeks", 21),
    ("1 Month", 30),
    ("2 Months", 60),
    ("3 Months", 90),
    ("4 Months", 120),
    ("5 Months", 150),
    ("6 Months", 180),
]


class AttachmentLoaderThread(QThread):
    """Background thread for loading attachments from Outlook"""
    finished = pyqtSignal(list, str)  # attachments list, error message
    progress = pyqtSignal(str)  # status message
    attachment_found = pyqtSignal(dict)  # Individual attachment to cache
    
    def __init__(self, days: int = 14, scan_from_date: datetime = None, parent=None):
        super().__init__(parent)
        self.days = days
        self.scan_from_date = scan_from_date  # If set, only scan from this date to now
        self._stop_requested = False  # Flag to stop scan early
    
    def request_stop(self):
        """Request the scan to stop early"""
        self._stop_requested = True
    
    def run(self):
        """Load attachments in background thread"""
        try:
            from suiteview.core.outlook_manager import OutlookManager
            import win32com.client
            import pywintypes
            
            # Create fresh Outlook connection in this thread
            outlook = OutlookManager()
            
            if not outlook.is_connected():
                self.finished.emit([], "Not connected to Outlook. Please ensure Outlook is running.")
                return
            
            self.progress.emit("Finding all Inbox folders...")
            
            # Get ALL inbox folders from ALL accounts
            inbox_folders = []
            try:
                namespace = outlook.namespace
                # Iterate through all stores (accounts)
                for store in namespace.Stores:
                    try:
                        store_name = store.DisplayName
                        self.progress.emit(f"Checking account: {store_name}...")
                        
                        # Try to get Inbox from this store
                        try:
                            # GetDefaultFolder on store's root
                            root_folder = store.GetRootFolder()
                            for folder in root_folder.Folders:
                                if folder.Name.lower() in ['inbox', 'posteingang', 'boîte de réception']:
                                    inbox_folders.append((store_name, folder))
                                    logger.info(f"Found Inbox in: {store_name}")
                                    break
                        except Exception as e:
                            logger.debug(f"Could not get inbox from store {store_name}: {e}")
                    except Exception as e:
                        logger.debug(f"Error accessing store: {e}")
            except Exception as e:
                logger.warning(f"Could not enumerate stores: {e}")
            
            # Fallback to default inbox if no stores found
            if not inbox_folders:
                self.progress.emit("Using default Inbox...")
                default_inbox = outlook.get_inbox_folder()
                if default_inbox:
                    inbox_folders.append(("Default", default_inbox))
            
            if not inbox_folders:
                self.finished.emit([], "Could not access any Inbox folder")
                return
            
            self.progress.emit(f"Scanning {len(inbox_folders)} Inbox folder(s)...")
            
            # Calculate the date range
            if self.scan_from_date:
                # Incremental scan - only get emails newer than what we have
                start_date = self.scan_from_date
                period_desc = "new emails"
            else:
                # Full scan for the period
                start_date = datetime.now() - timedelta(days=self.days)
                period_desc = f"last {self.days} days"
            
            date_filter = start_date.strftime("%m/%d/%Y %H:%M %p")
            
            self.progress.emit(f"Filtering to {period_desc}...")
            
            attachments = []
            count = 0
            emails_with_attachments = 0
            max_emails_per_inbox = 5000  # Limit per inbox
            skipped_no_attachments = 0
            skipped_inline_only = 0
            stopped_early = False
            
            # Scan ALL inbox folders
            for store_name, inbox in inbox_folders:
                if self._stop_requested:
                    stopped_early = True
                    break
                    
                self.progress.emit(f"Scanning: {store_name}...")
                logger.info(f"Scanning inbox from: {store_name}")
                
                try:
                    items = inbox.Items
                    items.Sort("[ReceivedTime]", True)  # Sort by date descending (newest first)
                except Exception as e:
                    logger.warning(f"Could not access items in {store_name}: {e}")
                    continue
                
                inbox_email_count = 0
                emails_checked = 0
                
                for item in items:
                    # Check if stop was requested
                    if self._stop_requested:
                        stopped_early = True
                        break
                    
                    if inbox_email_count >= max_emails_per_inbox:
                        break
                    
                    emails_checked += 1
                    if emails_checked % 50 == 0:
                        self.progress.emit(f"Checking email {emails_checked} in {store_name}... ({len(attachments)} attachments found)")
                    
                    try:
                        # Only process MailItem objects
                        if item.Class != 43:
                            continue
                        
                        # Check date
                        received_time = None
                        try:
                            received_time = item.ReceivedTime
                            # Convert COM datetime to Python datetime for comparison
                            if received_time:
                                # pywintypes.datetime can be compared directly, but let's be safe
                                import pywintypes
                                if isinstance(received_time, pywintypes.TimeType):
                                    received_time = datetime(
                                        received_time.year, received_time.month, received_time.day,
                                        received_time.hour, received_time.minute, received_time.second
                                    )
                            # Stop if email is older than our date range
                            if received_time and received_time < start_date:
                                break  # Since sorted by date desc, we can stop here
                        except Exception as date_err:
                            logger.debug(f"Error checking date: {date_err}")
                            continue
                        
                        # Check for attachments
                        try:
                            attach_count = item.Attachments.Count
                            if attach_count == 0:
                                skipped_no_attachments += 1
                                continue
                        except:
                            continue
                        
                        # Get sender email address directly - works for ALL senders (internal and external)
                        sender_display = "(Unknown)"
                        try:
                            # Get the email address directly - this works for everyone
                            sender_email = item.SenderEmailAddress
                            
                            if sender_email:
                                # Check if it's an Exchange X500 address (internal users)
                                if sender_email.startswith('/O=') or sender_email.startswith('/o='):
                                    # Try to resolve to SMTP address for internal Exchange users
                                    try:
                                        sender_display = item.Sender.GetExchangeUser().PrimarySmtpAddress
                                    except:
                                        # Fallback to SenderName for internal users
                                        sender_display = item.SenderName or sender_email
                                else:
                                    # External SMTP sender - use the email address directly
                                    sender_display = sender_email
                            else:
                                # No email address, try SenderName as last resort
                                sender_display = item.SenderName or "(Unknown)"
                        except Exception as sender_err:
                            logger.debug(f"Error getting sender: {sender_err}")
                            # Try SenderName as absolute fallback
                            try:
                                sender_display = item.SenderName or "(Unknown)"
                            except:
                                sender_display = "(Unknown)"
                        
                        email_id = None
                        try:
                            email_id = item.EntryID
                        except:
                            continue
                        
                        # Process attachments
                        found_real_attachment = False
                        for idx, attachment in enumerate(item.Attachments, 1):
                            try:
                                # Get filename first
                                filename = attachment.FileName
                                if not filename:
                                    continue
                                
                                # Check attachment type
                                # Type 1 = olByValue (file attachment)
                                # Type 5 = olEmbeddeditem (embedded message - .msg files)
                                attach_type = attachment.Type
                                # Accept type 1, and type 5 if it's a .msg file
                                if attach_type not in [1, 5]:
                                    continue
                                if attach_type == 5 and not filename.lower().endswith('.msg'):
                                    continue
                                
                                # Get file extension
                                ext = filename.lower().split('.')[-1] if '.' in filename else ''
                                
                                # Only skip small images that are likely signatures or inline
                                # Don't skip documents (.msg, .docx, .pdf, .xlsx, etc.) even if they have Content-ID
                                # Some email clients add Content-ID to all attachments
                                skip_attachment = False
                                try:
                                    size = attachment.Size
                                    # Only filter out small images (under 15KB) - these are likely signatures
                                    if ext in ['png', 'gif', 'jpg', 'jpeg', 'bmp']:
                                        if size < 15000:
                                            skip_attachment = True  # Small image, likely signature
                                except:
                                    pass
                                
                                if skip_attachment:
                                    continue
                                
                                found_real_attachment = True
                                attach_data = {
                                    'sender': sender_display,
                                    'date': received_time,
                                    'attachment_name': filename,
                                    'email_id': email_id,
                                    'attachment_index': idx
                                }
                                attachments.append(attach_data)
                                # Signal to cache this attachment
                                self.attachment_found.emit(attach_data)
                            except Exception as attach_err:
                                logger.debug(f"Error processing attachment: {attach_err}")
                                continue
                        
                        if found_real_attachment:
                            emails_with_attachments += 1
                            inbox_email_count += 1
                        else:
                            skipped_inline_only += 1
                        
                        count += 1
                        if count % 100 == 0:
                            self.progress.emit(f"Scanned {count} emails, found {len(attachments)} attachments...")
                        
                    except Exception as e:
                        logger.debug(f"Error processing email: {e}")
                        continue
                
                if stopped_early:
                    break
                    
                logger.info(f"Finished scanning {store_name}: found {inbox_email_count} emails with attachments")
            
            if stopped_early:
                logger.info(f"Scan stopped early: {len(attachments)} attachments from {emails_with_attachments} emails")
                self.progress.emit(f"Stopped: Found {len(attachments)} attachments from {emails_with_attachments} emails")
            else:
                logger.info(f"Scan complete: {len(attachments)} attachments from {emails_with_attachments} emails. "
                           f"Skipped: {skipped_no_attachments} no attachments, {skipped_inline_only} inline-only")
                self.progress.emit(f"Found {len(attachments)} attachments from {emails_with_attachments} emails")
            self.finished.emit(attachments, "")
            
        except Exception as e:
            logger.error(f"Failed to load attachments: {e}")
            self.finished.emit([], f"Error: {str(e)}")


class EmailAttachmentsWindow(QWidget):
    """Simple email attachments viewer with FilterTableView"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.outlook = get_outlook_manager()
        self.repo = get_email_repository()
        self.attachment_data = None
        self._scan_days = 14  # Default scan period
        
        # Load saved scan period from database
        saved_period = self.repo.get_setting('attachment_scan_days', '14')
        try:
            self._scan_days = int(saved_period)
        except:
            self._scan_days = 14
        
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
        self._loader_thread = None
        
        self.init_ui()
        # Defer loading until after window is shown
        QTimer.singleShot(100, self.load_attachments)
        
        # Bring window to front
        self.raise_()
        self.activateWindow()
        
        logger.info("Email Attachments Window initialized")
    
    def init_ui(self):
        """Initialize the UI with SuiteView theme"""
        self.setWindowTitle("SuiteView - Email Attachments")
        self.resize(900, 600)
        
        # Set gold border on the window
        self.setStyleSheet("""
            EmailAttachmentsWindow {
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
        
        # Refresh button
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setFixedSize(28, 28)
        self.refresh_btn.setToolTip("Refresh Attachments")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 2px solid #D4A017;
                border-radius: 4px;
                color: #D4A017;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(212, 160, 23, 0.2);
                border-color: #FFD700;
                color: #FFD700;
            }
            QPushButton:pressed {
                background: rgba(212, 160, 23, 0.4);
            }
        """)
        self.refresh_btn.clicked.connect(self.load_attachments)
        header_layout.addWidget(self.refresh_btn)
        
        # Hide PNG toggle button
        self.hide_png_btn = QPushButton("🖼 Hide PNG")
        self.hide_png_btn.setFixedHeight(28)
        self.hide_png_btn.setCheckable(True)
        self.hide_png_btn.setChecked(False)
        self.hide_png_btn.setToolTip("Toggle to hide/show PNG image attachments")
        self.hide_png_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hide_png_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 2px solid #D4A017;
                border-radius: 4px;
                color: #D4A017;
                font-size: 9px;
                font-weight: bold;
                padding: 2px 8px;
            }
            QPushButton:hover {
                background: rgba(212, 160, 23, 0.2);
                border-color: #FFD700;
                color: #FFD700;
            }
            QPushButton:checked {
                background: #D4A017;
                color: #0D3A7A;
            }
            QPushButton:checked:hover {
                background: #FFD700;
            }
        """)
        self.hide_png_btn.clicked.connect(self._on_hide_png_toggled)
        header_layout.addWidget(self.hide_png_btn)
        
        # Title in center
        self.title_label = QLabel("📎 EMAIL ATTACHMENTS")
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
        
        # Window control buttons
        window_btn_style = """
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 0px;
                padding: 0px;
                min-width: 36px;
                max-width: 36px;
                min-height: 24px;
                max-height: 24px;
                font-size: 14px;
                font-weight: bold;
            }
        """
        
        # Minimize button
        self.minimize_btn = QPushButton("–")
        self.minimize_btn.setStyleSheet(window_btn_style + """
            QPushButton { color: #D4A017; }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.15); color: #FFD700; }
        """)
        self.minimize_btn.setToolTip("Minimize")
        self.minimize_btn.clicked.connect(self.showMinimized)
        header_layout.addWidget(self.minimize_btn)
        
        # Maximize/Restore button
        self.maximize_btn = QPushButton("□")
        self.maximize_btn.setStyleSheet(window_btn_style + """
            QPushButton { color: #D4A017; }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.15); color: #FFD700; }
        """)
        self.maximize_btn.setToolTip("Maximize")
        self.maximize_btn.clicked.connect(self._toggle_maximize)
        header_layout.addWidget(self.maximize_btn)
        
        # Close button
        self.close_btn = QPushButton("✕")
        self.close_btn.setStyleSheet(window_btn_style + """
            QPushButton { color: #D4A017; }
            QPushButton:hover { background-color: #E81123; color: white; }
        """)
        self.close_btn.setToolTip("Close")
        self.close_btn.clicked.connect(self.close)
        header_layout.addWidget(self.close_btn)
        
        main_layout.addWidget(self.header_bar)
        
        # Content area
        content = QFrame()
        content.setStyleSheet("""
            QFrame {
                background-color: #E8EEF5;
                border: none;
            }
        """)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(4)
        
        # Attachments grid using FilterTableView
        self.attachments_grid = FilterTableView()
        self.attachments_grid.setStyleSheet("""
            QTableView {
                background-color: white;
                border: 1px solid #6B8DC9;
                gridline-color: transparent;
                selection-background-color: #FFFDE7;
                selection-color: black;
            }
            QTableView::item {
                padding: 2px 4px;
                background-color: white;
            }
            QHeaderView::section {
                background-color: #1E5BA8;
                color: white;
                padding: 4px;
                border: none;
                border-right: 1px solid #0D3A7A;
                font-weight: bold;
                font-size: 10px;
            }
        """)
        # Hide the row index (vertical header)
        if hasattr(self.attachments_grid, 'table_view'):
            self.attachments_grid.table_view.verticalHeader().setVisible(False)
            self.attachments_grid.table_view.setShowGrid(False)
            self.attachments_grid.table_view.setAlternatingRowColors(False)
            # Set file icon delegate for the Attachment column (column 4)
            self.file_icon_delegate = FileIconDelegate(self.attachments_grid.table_view)
            self.attachments_grid.table_view.setItemDelegateForColumn(4, self.file_icon_delegate)
        content_layout.addWidget(self.attachments_grid)
        
        # Connect double-click handler
        if hasattr(self.attachments_grid, 'table_view'):
            self.attachments_grid.table_view.doubleClicked.connect(self.on_double_click)
        
        # Status bar
        self.status_label = QLabel("Loading attachments...")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #666;
                padding: 2px 4px;
                font-size: 9px;
                background: transparent;
            }
        """)
        content_layout.addWidget(self.status_label)
        
        main_layout.addWidget(content, stretch=1)
        
        # Footer bar
        footer = QFrame()
        footer.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #082B5C, stop:0.5 #0D3A7A, stop:1 #1E5BA8);
                border: none;
                border-top: 2px solid #D4A017;
            }
        """)
        footer.setFixedHeight(32)
        
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(8, 2, 8, 2)
        footer_layout.setSpacing(8)
        
        # Footer hint text
        hint_label = QLabel("Double-click Attachment to open file • Double-click other columns to open email")
        hint_label.setStyleSheet("""
            QLabel {
                color: #D4A017;
                font-size: 9px;
                background: transparent;
            }
        """)
        footer_layout.addWidget(hint_label)
        footer_layout.addStretch()
        
        # Scan period label
        period_label = QLabel("Scan Period:")
        period_label.setStyleSheet("QLabel { color: #D4A017; font-size: 9px; background: transparent; }")
        footer_layout.addWidget(period_label)
        
        # Scan period dropdown
        self.period_combo = QComboBox()
        self.period_combo.setFixedWidth(100)
        self.period_combo.setFixedHeight(22)
        self.period_combo.setStyleSheet("""
            QComboBox {
                background-color: #1E5BA8;
                color: white;
                border: 1px solid #D4A017;
                border-radius: 2px;
                padding: 2px 6px;
                font-size: 9px;
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
                color: white;
                selection-background-color: #3A7DC8;
                border: 1px solid #D4A017;
            }
        """)
        
        # Add period options
        selected_index = 2  # Default to "2 Weeks"
        for i, (label, days) in enumerate(SCAN_PERIODS):
            self.period_combo.addItem(label, days)
            if days == self._scan_days:
                selected_index = i
        self.period_combo.setCurrentIndex(selected_index)
        footer_layout.addWidget(self.period_combo)
        
        # Rescan button
        self.rescan_btn = QPushButton("Rescan")
        self.rescan_btn.setFixedHeight(22)
        self.rescan_btn.setStyleSheet("""
            QPushButton {
                background-color: #D4A017;
                color: #0D3A7A;
                border: none;
                border-radius: 2px;
                padding: 2px 12px;
                font-size: 9px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FFD700;
            }
            QPushButton:pressed {
                background-color: #B8860B;
            }
            QPushButton:disabled {
                background-color: #666;
                color: #999;
            }
        """)
        self.rescan_btn.clicked.connect(self._on_rescan_clicked)
        footer_layout.addWidget(self.rescan_btn)
        
        # Stop Scan button
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setFixedHeight(22)
        self.stop_btn.setEnabled(False)  # Only enabled during scan
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                border: none;
                border-radius: 2px;
                padding: 2px 12px;
                font-size: 9px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
            QPushButton:pressed {
                background-color: #A93226;
            }
            QPushButton:disabled {
                background-color: #666;
                color: #999;
            }
        """)
        self.stop_btn.setToolTip("Stop the current scan and show results collected so far")
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        footer_layout.addWidget(self.stop_btn)
        
        # Clear Cache button
        self.clear_btn = QPushButton("Clear Cache")
        self.clear_btn.setFixedHeight(22)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #7F8C8D;
                color: white;
                border: none;
                border-radius: 2px;
                padding: 2px 12px;
                font-size: 9px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #95A5A6;
            }
            QPushButton:pressed {
                background-color: #5D6D7E;
            }
            QPushButton:disabled {
                background-color: #444;
                color: #999;
            }
        """)
        self.clear_btn.setToolTip("Clear all cached attachments - next scan will start fresh")
        self.clear_btn.clicked.connect(self._on_clear_cache_clicked)
        footer_layout.addWidget(self.clear_btn)
        
        main_layout.addWidget(footer)
        
        # Add size grip for resizing
        self.size_grip = QSizeGrip(self)
        self.size_grip.setStyleSheet("QSizeGrip { background-color: transparent; width: 16px; height: 16px; }")
    
    def _on_rescan_clicked(self):
        """Handle rescan button click - save period and reload"""
        # Get selected period
        days = self.period_combo.currentData()
        self._scan_days = days
        
        # Save to database
        self.repo.set_setting('attachment_scan_days', str(days))
        
        # Reload attachments with new period (force full scan)
        self.load_attachments(force_full_scan=True)
    
    def _on_stop_clicked(self):
        """Handle stop button click - stop the scan and show results so far"""
        if self._loader_thread and self._loader_thread.isRunning():
            self.status_label.setText("Stopping scan...")
            self._loader_thread.request_stop()
            self.stop_btn.setEnabled(False)
    
    def _on_hide_png_toggled(self, checked):
        """Handle hide PNG toggle - filter out or show PNG files"""
        # The Type column is named "Type" in the display DataFrame
        type_column = "Type"
        
        if checked:
            self.hide_png_btn.setText("🖼 Show PNG")
            # Exclude PNG from view
            if hasattr(self.attachments_grid, 'df') and self.attachments_grid.df is not None:
                # Get all unique types
                all_types = set(str(v) if not pd.isna(v) else "(Blanks)" 
                               for v in self.attachments_grid.df[type_column].unique())
                # Get current filter for Type column (if any)
                current_filter = self.attachments_grid.column_filters.get(type_column, None)
                
                if current_filter is None:
                    # No filter exists - include all except PNG
                    new_filter = all_types - {'PNG'}
                else:
                    # Remove PNG from existing filter
                    new_filter = current_filter - {'PNG'}
                
                # Apply the filter
                self.attachments_grid.column_filters[type_column] = new_filter
                self.attachments_grid.filtered_columns.add(type_column)
                self.attachments_grid.apply_all_filters()
                self.attachments_grid.update_header_indicators()
        else:
            self.hide_png_btn.setText("🖼 Hide PNG")
            # Restore PNG to view
            if hasattr(self.attachments_grid, 'df') and self.attachments_grid.df is not None:
                # Get all unique types
                all_types = set(str(v) if not pd.isna(v) else "(Blanks)" 
                               for v in self.attachments_grid.df[type_column].unique())
                current_filter = self.attachments_grid.column_filters.get(type_column, None)
                
                if current_filter is not None:
                    # Add PNG back to the filter
                    new_filter = current_filter | {'PNG'}
                    
                    # If all types are now selected, remove the filter entirely
                    if new_filter >= all_types:
                        del self.attachments_grid.column_filters[type_column]
                        self.attachments_grid.filtered_columns.discard(type_column)
                    else:
                        self.attachments_grid.column_filters[type_column] = new_filter
                    
                    self.attachments_grid.apply_all_filters()
                    self.attachments_grid.update_header_indicators()
    
    def _on_clear_cache_clicked(self):
        """Handle clear cache button click - clear all cached attachments"""
        reply = QMessageBox.question(
            self,
            "Clear Attachment Cache",
            "This will clear all cached attachment data.\n\nThe next scan will retrieve all attachments fresh from Outlook.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.repo.clear_cache()  # Clear all cached data
                self.attachment_data = None
                self.attachments_grid.set_dataframe(pd.DataFrame())  # Clear the grid
                self.status_label.setText("Cache cleared. Click Rescan to load attachments fresh.")
                logger.info("Attachment cache cleared by user")
            except Exception as e:
                logger.error(f"Error clearing cache: {e}")
                QMessageBox.warning(self, "Error", f"Failed to clear cache: {e}")
    
    def load_attachments(self, force_full_scan=False):
        """Load recent attachments - uses cache when possible"""
        # Disable buttons during load
        self.refresh_btn.setEnabled(False)
        self.rescan_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)  # Enable stop button during scan
        
        # Calculate the date range for the requested period
        requested_start = datetime.now() - timedelta(days=self._scan_days)
        
        # Check if we have cached data that covers the requested period
        cached_attachments = []
        scan_from_date = None
        
        if not force_full_scan:
            # Try to load from cache first
            self.status_label.setText("Checking cached data...")
            cached_attachments = self.repo.get_attachments_since(requested_start)
            
            if cached_attachments:
                # We have some cached data - check if we need to scan for newer emails
                newest_cached = self.repo.get_newest_attachment_date()
                if newest_cached:
                    # Only scan for emails newer than our newest cached
                    scan_from_date = newest_cached
                    self.status_label.setText(f"Found {len(cached_attachments)} cached, checking for new...")
                else:
                    self.status_label.setText(f"Loaded {len(cached_attachments)} from cache")
        
        # Start background thread for new emails
        self._loader_thread = AttachmentLoaderThread(
            days=self._scan_days, 
            scan_from_date=scan_from_date,
            parent=self
        )
        self._loader_thread.progress.connect(self._on_load_progress)
        self._loader_thread.attachment_found.connect(self._on_attachment_found)
        self._loader_thread.finished.connect(
            lambda new_attach, err: self._on_load_finished(new_attach, err, cached_attachments)
        )
        self._loader_thread.start()
    
    def _on_attachment_found(self, attachment):
        """Cache individual attachment as it's found"""
        try:
            self.repo.save_attachment_simple(attachment)
        except Exception as e:
            logger.debug(f"Failed to cache attachment: {e}")
    
    def _on_load_progress(self, message):
        """Update status during background load"""
        self.status_label.setText(message)
    
    def _on_load_finished(self, new_attachments, error, cached_attachments=None):
        """Handle completion of background load"""
        self.refresh_btn.setEnabled(True)
        self.rescan_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)  # Disable stop button when scan complete
        
        if error:
            self.status_label.setText(error)
            return
        
        # Combine cached and new attachments
        cached_attachments = cached_attachments or []
        
        # Convert cached attachments to same format as new ones
        all_attachments = []
        
        # Add new attachments first (they're newer)
        for attach in new_attachments:
            all_attachments.append(attach)
        
        # Add cached attachments (convert from DB format)
        for cached in cached_attachments:
            # Check if this email_id + attachment_index combo already exists in new
            is_duplicate = any(
                a['email_id'] == cached['email_id'] and 
                a['attachment_index'] == cached['attachment_index']
                for a in new_attachments
            )
            if not is_duplicate:
                # Parse the cached date
                cached_date = cached.get('email_date')
                if cached_date:
                    if isinstance(cached_date, str):
                        try:
                            cached_date = datetime.fromisoformat(cached_date)
                        except:
                            cached_date = datetime.now()
                else:
                    cached_date = datetime.now()
                
                all_attachments.append({
                    'sender': cached['email_sender'],
                    'date': cached_date,
                    'attachment_name': cached['attachment_name'],
                    'email_id': cached['email_id'],
                    'attachment_index': cached['attachment_index']
                })
        
        if not all_attachments:
            period_text = self._get_period_text()
            self.status_label.setText(f"No attachments found in the {period_text}")
            return
        
        try:
            # Convert to DataFrame
            df = pd.DataFrame(all_attachments)
            
            # Handle dates - ensure they're all valid datetime objects (date only, no time)
            def safe_format_date(d):
                if d is None:
                    return "Unknown"
                try:
                    if hasattr(d, 'strftime'):
                        return d.strftime('%Y-%m-%d')
                    # Try parsing as string
                    return pd.to_datetime(d).strftime('%Y-%m-%d')
                except:
                    return "Unknown"
            
            df['Sent Date'] = df['date'].apply(safe_format_date)
            
            # Split sender into name and domain
            def get_sender_name(s):
                if not s or s == '(Unknown)':
                    return s or '(Unknown)'
                if '@' in s:
                    return s.split('@')[0]
                return s
            
            def get_sender_domain(s):
                if not s or s == '(Unknown)':
                    return ''
                if '@' in s:
                    return s.split('@')[1] if len(s.split('@')) > 1 else ''
                return ''
            
            df['Sender Name'] = df['sender'].apply(get_sender_name)
            df['Domain'] = df['sender'].apply(get_sender_domain)
            
            # Extract file type (extension) from attachment name
            def get_file_type(filename):
                if not filename:
                    return ''
                ext = os.path.splitext(filename)[1].upper()
                return ext[1:] if ext.startswith('.') else ext  # Remove leading dot
            
            df['File Type'] = df['attachment_name'].apply(get_file_type)
            
            # Sort by date descending (handle None values)
            df['sort_date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.sort_values('sort_date', ascending=False, na_position='last').reset_index(drop=True)
            df = df.drop('sort_date', axis=1)
            
            # Select and rename columns for display
            display_df = df[['Sender Name', 'Domain', 'Sent Date', 'File Type', 'attachment_name']].copy()
            display_df.columns = ['Sender', 'Domain', 'Sent Date', 'Type', 'Attachment']
            
            # Store original data for lookups
            self.attachment_data = df
            
            # Load into grid
            self.attachments_grid.set_dataframe(display_df)
            
            period_text = self._get_period_text()
            new_count = len(new_attachments)
            cached_count = len(all_attachments) - new_count
            
            if cached_count > 0 and new_count > 0:
                self.status_label.setText(f"Showing {len(all_attachments)} attachments ({new_count} new, {cached_count} cached) from {period_text}")
            elif cached_count > 0:
                self.status_label.setText(f"Showing {len(all_attachments)} attachments from cache ({period_text})")
            else:
                self.status_label.setText(f"Showing {len(all_attachments)} attachments from {period_text}")
            
        except Exception as e:
            logger.error(f"Failed to process attachments: {e}", exc_info=True)
            self.status_label.setText(f"Error processing attachments: {str(e)}")
    
    def _get_period_text(self):
        """Get human-readable period text"""
        for label, days in SCAN_PERIODS:
            if days == self._scan_days:
                return f"last {label.lower()}"
        return f"last {self._scan_days} days"
    
    def on_double_click(self, index):
        """Handle double-click on grid"""
        if self.attachment_data is None or self.attachment_data.empty:
            return
        
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
            if row < 0 or row >= len(self.attachment_data):
                return
            attachment = self.attachment_data.iloc[row]
        
        email_id = attachment['email_id']
        attachment_index = attachment['attachment_index']
        
        # Column 4 is Attachment - open attachment
        # Columns 0, 1, 2, 3 (Sender, Domain, Date, Type) - open email
        if col == 4:
            self.open_attachment(email_id, attachment_index)
        else:
            self.open_email(email_id)
    
    def open_email(self, email_id: str):
        """Open email in Outlook"""
        if not self.outlook.is_connected():
            QMessageBox.warning(
                self, "Outlook Not Connected",
                "Please ensure Microsoft Outlook is running."
            )
            return
        
        success = self.outlook.open_email(email_id)
        if not success:
            QMessageBox.warning(self, "Error", "Failed to open email")
    
    def open_attachment(self, email_id: str, attachment_index: int):
        """Open attachment with default application"""
        if not self.outlook.is_connected():
            QMessageBox.warning(
                self, "Outlook Not Connected",
                "Please ensure Microsoft Outlook is running."
            )
            return
        
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        
        try:
            temp_path = self.outlook.get_attachment_preview_path(email_id, attachment_index)
            QApplication.restoreOverrideCursor()
            
            if temp_path and os.path.exists(temp_path):
                os.startfile(temp_path)
            else:
                QMessageBox.warning(self, "Error", "Failed to retrieve attachment")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Error", f"Failed to open attachment: {e}")
    
    def _toggle_maximize(self):
        """Toggle maximize/restore"""
        if self._is_maximized:
            self.showNormal()
            self.maximize_btn.setText("□")
            self._is_maximized = False
        else:
            self.showMaximized()
            self.maximize_btn.setText("❐")
            self._is_maximized = True
    
    # ============ Window Drag and Resize ============
    
    def mousePressEvent(self, event):
        """Handle mouse press for dragging and resizing"""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            
            # Check if we're on a resize edge
            edge = self._get_resize_edge(pos)
            if edge:
                self._resizing = True
                self._resize_edge = edge
                self._start_geometry = self.geometry()
                self._start_pos = event.globalPosition().toPoint()
            elif self.header_bar.geometry().contains(pos):
                # Start drag if clicking on header
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging and resizing"""
        pos = event.position().toPoint()
        
        if self._resizing and self._resize_edge:
            self._do_resize(event.globalPosition().toPoint())
        elif self._drag_pos is not None:
            # Dragging window
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        else:
            # Update cursor based on position
            edge = self._get_resize_edge(pos)
            if edge in ['left', 'right']:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif edge in ['top', 'bottom']:
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            elif edge in ['top-left', 'bottom-right']:
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif edge in ['top-right', 'bottom-left']:
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release"""
        self._drag_pos = None
        self._resizing = False
        self._resize_edge = None
    
    def _get_resize_edge(self, pos):
        """Determine which edge the mouse is on"""
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
    
    def _do_resize(self, global_pos):
        """Perform resize based on edge being dragged"""
        if not self._start_geometry or not self._start_pos:
            return
        
        delta = global_pos - self._start_pos
        geo = self._start_geometry
        
        min_width = 400
        min_height = 300
        
        new_geo = self.geometry()
        
        if 'left' in self._resize_edge:
            new_width = geo.width() - delta.x()
            if new_width >= min_width:
                new_geo.setLeft(geo.left() + delta.x())
        if 'right' in self._resize_edge:
            new_width = geo.width() + delta.x()
            if new_width >= min_width:
                new_geo.setWidth(new_width)
        if 'top' in self._resize_edge:
            new_height = geo.height() - delta.y()
            if new_height >= min_height:
                new_geo.setTop(geo.top() + delta.y())
        if 'bottom' in self._resize_edge:
            new_height = geo.height() + delta.y()
            if new_height >= min_height:
                new_geo.setHeight(new_height)
        
        self.setGeometry(new_geo)
    
    def resizeEvent(self, event):
        """Handle resize to reposition size grip"""
        super().resizeEvent(event)
        # Position size grip at bottom-right corner
        grip_size = self.size_grip.sizeHint()
        self.size_grip.move(
            self.width() - grip_size.width() - 3,
            self.height() - grip_size.height() - 3
        )
