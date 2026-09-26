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

import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QMessageBox, QApplication, QComboBox, QFileIconProvider,
    QStyledItemDelegate, QStyle
)
from PyQt6.QtCore import Qt, QObject, QFileInfo, QUrl, QMimeData
from PyQt6.QtGui import QIcon

from suiteview.ui.widgets.filter_table_view import FilterTableView
from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from suiteview.ui.workers import WorkerController, WorkerSignals
from suiteview.core.outlook_manager import get_outlook_manager, close_thread_outlook_manager
from suiteview.data.repositories import get_email_repository

logger = logging.getLogger(__name__)

try:
    from pywintypes import com_error as OutlookComError
except ImportError:
    OutlookComError = None

OUTLOOK_COM_ERRORS = (AttributeError, TypeError, OSError) + (
    (OutlookComError,) if OutlookComError is not None else ()
)

# ============ Shared helper functions ============

_IMAGE_TYPES = {'PNG', 'JPG', 'JPEG', 'GIF', 'BMP', 'TIFF', 'TIF', 'ICO', 'WEBP', 'SVG'}


def _safe_format_date(d):
    """Format a date value to YYYY-MM-DD string, handling various input types"""
    if d is None:
        return "Unknown"
    try:
        if hasattr(d, 'strftime'):
            return d.strftime('%Y-%m-%d')
        return pd.to_datetime(d).strftime('%Y-%m-%d')
    except (ValueError, TypeError, AttributeError):
        logger.debug("Could not format email date %r", d, exc_info=True)
        return "Unknown"


def _get_sender_name(s):
    """Extract sender name (part before @) from email address"""
    if not s or s == '(Unknown)':
        return s or '(Unknown)'
    if '@' in s:
        return s.split('@')[0]
    return s


def _get_sender_domain(s):
    """Extract domain (part after @) from email address"""
    if not s or s == '(Unknown)':
        return ''
    if '@' in s:
        return s.split('@')[1] if len(s.split('@')) > 1 else ''
    return ''


def _get_file_type(filename):
    """Extract uppercase file extension from filename"""
    if not filename:
        return ''
    ext = os.path.splitext(filename)[1].upper()
    return ext[1:] if ext.startswith('.') else ext


def _format_file_size(num_bytes):
    """Format a byte count as a compact human-readable size (e.g. '12 KB', '3.4 MB')."""
    try:
        size = float(num_bytes)
    except (TypeError, ValueError):
        return ''
    if size <= 0:
        return ''
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            if unit == 'B':
                return f"{int(size)} {unit}"
            if size < 10:
                return f"{size:.1f} {unit}"
            return f"{int(round(size))} {unit}"
        size /= 1024
    return f"{int(round(size))} TB"


def _process_attachment_dataframe(df):
    """Apply standard column transformations, filtering, and sorting to an attachment DataFrame.
    
    Expects columns: 'date', 'sender', 'attachment_name', 'email_id', 'attachment_index'.
    Returns (display_df, full_df) or (None, None) if empty after filtering.
    """
    df['Sent Date'] = df['date'].apply(_safe_format_date)
    df['Full Name'] = df['sender_name'].fillna('')
    df['Sender Name'] = df['sender'].apply(_get_sender_name)
    df['Domain'] = df['sender'].apply(_get_sender_domain)
    df['Subject'] = df['email_subject'].fillna('')
    df['File Type'] = df['attachment_name'].apply(_get_file_type)
    if 'attachment_size' not in df.columns:
        df['attachment_size'] = 0
    df['File Size'] = df['attachment_size'].apply(_format_file_size)
    
    # Filter out embedded image types - show only true file attachments
    df = df[~df['File Type'].str.upper().isin(_IMAGE_TYPES)].reset_index(drop=True)
    
    if df.empty:
        return None, None
    
    # Sort by date descending
    df['sort_date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.sort_values('sort_date', ascending=False, na_position='last').reset_index(drop=True)
    df = df.drop('sort_date', axis=1)
    
    # Select and rename columns for display
    display_df = df[['Full Name', 'Sender Name', 'Domain', 'Sent Date', 'Subject', 'File Type', 'File Size', 'attachment_name']].copy()
    display_df.columns = ['Full Name', 'Sender', 'Domain', 'Sent Date', 'Subject', 'Type', 'Size', 'Attachment']
    
    return display_df, df


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


class AttachmentLoaderWorker(QObject):
    """Worker that traverses Outlook folders and maps visible attachments."""
    
    def __init__(self, days: int = 14, scan_from_date: datetime = None, parent=None):
        super().__init__(parent)
        self.signals = WorkerSignals(self)
        self.days = days
        self.scan_from_date = scan_from_date  # If set, only scan from this date to now
        self._stop_requested = False  # Flag to stop scan early
    
    def cancel(self):
        """Request the scan to stop early"""
        self._stop_requested = True

    def _emit_status(self, message: str) -> None:
        self.signals.progress.emit({"kind": "status", "message": message})

    def _emit_attachment(self, attachment: dict) -> None:
        self.signals.progress.emit({"kind": "attachment", "attachment": attachment})
    
    def run(self):
        """Load attachments in the worker thread."""
        try:
            outlook = get_outlook_manager()
            if not outlook.is_connected():
                self.signals.error.emit(
                    "Not connected to Outlook. Please ensure Outlook is running."
                )
                return

            inbox_folders = self._find_inbox_folders(outlook)
            if not inbox_folders:
                self.signals.error.emit("Could not access any Inbox folder")
                return

            start_date, period_desc = self._scan_window()
            self._emit_status(f"Filtering to {period_desc}...")
            summary = self._scan_inboxes(inbox_folders, start_date)
            self._finish_scan(summary)
        except Exception as e:
            logger.error(f"Failed to load attachments: {e}")
            self.signals.error.emit(f"Error: {str(e)}")
        finally:
            try:
                close_thread_outlook_manager()
            except Exception:
                logger.debug(
                    "Ignoring Outlook cleanup failure after attachment scan",
                    exc_info=True,
                )
            self.signals.finished.emit()

    def _find_inbox_folders(self, outlook):
        """Find Inbox folders across Outlook stores, falling back to default."""
        self._emit_status("Finding all Inbox folders...")
        inbox_folders = []
        try:
            namespace = outlook.namespace
            for store in namespace.Stores:
                try:
                    store_name = store.DisplayName
                    self._emit_status(f"Checking account: {store_name}...")
                    self._append_store_inbox(inbox_folders, store_name, store)
                except Exception as e:
                    logger.debug(f"Error accessing store: {e}")
        except Exception as e:
            logger.warning(f"Could not enumerate stores: {e}")

        if not inbox_folders:
            self._emit_status("Using default Inbox...")
            default_inbox = outlook.get_inbox_folder()
            if default_inbox:
                inbox_folders.append(("Default", default_inbox))

        if inbox_folders:
            self._emit_status(f"Scanning {len(inbox_folders)} Inbox folder(s)...")
        return inbox_folders

    def _append_store_inbox(self, inbox_folders, store_name, store) -> None:
        try:
            root_folder = store.GetRootFolder()
            for folder in root_folder.Folders:
                if folder.Name.lower() in ["inbox", "posteingang", "boîte de réception"]:
                    inbox_folders.append((store_name, folder))
                    logger.info(f"Found Inbox in: {store_name}")
                    break
        except Exception as e:
            logger.debug(f"Could not get inbox from store {store_name}: {e}")

    def _scan_window(self):
        if self.scan_from_date:
            return self.scan_from_date, "new emails"
        return datetime.now() - timedelta(days=self.days), f"last {self.days} days"

    def _scan_inboxes(self, inbox_folders, start_date):
        summary = {
            "attachments": [],
            "emails_with_attachments": 0,
            "skipped_no_attachments": 0,
            "skipped_inline_only": 0,
            "stopped_early": False,
            "processed_count": 0,
        }
        for store_name, inbox in inbox_folders:
            if self._stop_requested:
                summary["stopped_early"] = True
                break
            self._scan_one_inbox(store_name, inbox, start_date, summary)
            if summary["stopped_early"]:
                break
        return summary

    def _scan_one_inbox(self, store_name, inbox, start_date, summary) -> None:
        self._emit_status(f"Scanning: {store_name}...")
        logger.info(f"Scanning inbox from: {store_name}")
        try:
            items = inbox.Items
            items.Sort("[ReceivedTime]", True)
        except Exception as e:
            logger.warning(f"Could not access items in {store_name}: {e}")
            return

        inbox_email_count = 0
        emails_checked = 0
        max_emails_per_inbox = 5000
        for item in items:
            if self._stop_requested:
                summary["stopped_early"] = True
                break
            if inbox_email_count >= max_emails_per_inbox:
                break
            emails_checked += 1
            if emails_checked % 50 == 0:
                self._emit_status(
                    f"Checking email {emails_checked} in {store_name}... "
                    f"({len(summary['attachments'])} attachments found)"
                )
            outcome = self._scan_mail_item(item, start_date, summary)
            if outcome == "older":
                break
            if outcome == "with_attachment":
                inbox_email_count += 1

        logger.info(
            f"Finished scanning {store_name}: found "
            f"{inbox_email_count} emails with attachments"
        )

    def _scan_mail_item(self, item, start_date, summary) -> str:
        try:
            if item.Class != 43:
                return "ignored"
            received_time = self._received_time(item)
            if received_time and received_time < start_date:
                return "older"
            attach_count = item.Attachments.Count
            if attach_count == 0:
                summary["skipped_no_attachments"] += 1
                return "no_attachment"

            sender_display, sender_full_name = self._sender_details(item)
            email_subject = self._email_subject(item)
            email_id = item.EntryID
            found_real_attachment = self._collect_attachments(
                item,
                received_time,
                sender_display,
                sender_full_name,
                email_subject,
                email_id,
                summary["attachments"],
            )
            if found_real_attachment:
                summary["emails_with_attachments"] += 1
                outcome = "with_attachment"
            else:
                summary["skipped_inline_only"] += 1
                outcome = "inline_only"
            summary["processed_count"] += 1
            if summary["processed_count"] % 100 == 0:
                self._emit_status(
                    f"Scanned {summary['processed_count']} emails, "
                    f"found {len(summary['attachments'])} attachments..."
                )
            return outcome
        except OUTLOOK_COM_ERRORS:
            logger.debug("Could not process Outlook email item", exc_info=True)
            return "error"
        except Exception as e:
            logger.debug(f"Error processing email: {e}")
            return "error"

    def _received_time(self, item):
        try:
            received_time = item.ReceivedTime
            if received_time:
                import pywintypes

                if isinstance(received_time, pywintypes.TimeType):
                    return datetime(
                        received_time.year,
                        received_time.month,
                        received_time.day,
                        received_time.hour,
                        received_time.minute,
                        received_time.second,
                    )
            return received_time
        except Exception as date_err:
            logger.debug(f"Error checking date: {date_err}")
            return None

    def _sender_details(self, item):
        sender_full_name = ""
        try:
            sender_full_name = item.SenderName or ""
        except Exception:
            sender_full_name = ""
        try:
            sender_email = getattr(item, "SenderEmailAddress", None)
            if not sender_email:
                return item.SenderName or "(Unknown)", sender_full_name
            if sender_email.startswith("/O=") or sender_email.startswith("/o="):
                try:
                    return item.Sender.GetExchangeUser().PrimarySmtpAddress, sender_full_name
                except OUTLOOK_COM_ERRORS:
                    logger.debug(
                        "Could not resolve Exchange sender while scanning attachments",
                        exc_info=True,
                    )
                    return item.SenderName or sender_email, sender_full_name
            return sender_email, sender_full_name
        except Exception as sender_err:
            logger.debug(f"Error getting sender: {sender_err}")
            try:
                return item.SenderName or "(Unknown)", sender_full_name
            except OUTLOOK_COM_ERRORS:
                logger.debug(
                    "Could not read Outlook SenderName fallback",
                    exc_info=True,
                )
                return "(Unknown)", sender_full_name

    @staticmethod
    def _email_subject(item) -> str:
        try:
            return item.Subject or ""
        except Exception:
            return ""

    def _collect_attachments(
        self,
        item,
        received_time,
        sender_display,
        sender_full_name,
        email_subject,
        email_id,
        attachments,
    ) -> bool:
        found_real_attachment = False
        for idx, attachment in enumerate(item.Attachments, 1):
            try:
                attach_data = self._map_attachment(
                    attachment,
                    idx,
                    received_time,
                    sender_display,
                    sender_full_name,
                    email_subject,
                    email_id,
                )
                if attach_data is None:
                    continue
                found_real_attachment = True
                attachments.append(attach_data)
                self._emit_attachment(attach_data)
            except Exception as attach_err:
                logger.debug(f"Error processing attachment: {attach_err}")
        return found_real_attachment

    def _map_attachment(
        self,
        attachment,
        idx,
        received_time,
        sender_display,
        sender_full_name,
        email_subject,
        email_id,
    ):
        filename = attachment.FileName
        if not filename:
            return None
        attach_type = attachment.Type
        if attach_type not in [1, 5]:
            return None
        if attach_type == 5 and not filename.lower().endswith(".msg"):
            return None
        if self._attachment_hidden(attachment):
            return None
        return {
            "sender": sender_display,
            "sender_name": sender_full_name,
            "email_subject": email_subject,
            "date": received_time,
            "attachment_name": filename,
            "attachment_size": getattr(attachment, "Size", 0),
            "email_id": email_id,
            "attachment_index": idx,
        }

    @staticmethod
    def _attachment_hidden(attachment) -> bool:
        try:
            pr_attach_hidden = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"
            return bool(attachment.PropertyAccessor.GetProperty(pr_attach_hidden))
        except OUTLOOK_COM_ERRORS:
            logger.debug(
                "Could not read Outlook attachment hidden property; assuming visible",
                exc_info=True,
            )
            return False

    def _finish_scan(self, summary) -> None:
        attachments = summary["attachments"]
        emails_with_attachments = summary["emails_with_attachments"]
        if summary["stopped_early"]:
            logger.info(
                f"Scan stopped early: {len(attachments)} attachments from "
                f"{emails_with_attachments} emails"
            )
            self._emit_status(
                f"Stopped: Found {len(attachments)} attachments from "
                f"{emails_with_attachments} emails"
            )
            self.signals.cancelled.emit()
        else:
            logger.info(
                f"Scan complete: {len(attachments)} attachments from "
                f"{emails_with_attachments} emails. Skipped: "
                f"{summary['skipped_no_attachments']} no attachments, "
                f"{summary['skipped_inline_only']} inline-only"
            )
            self._emit_status(
                f"Found {len(attachments)} attachments from "
                f"{emails_with_attachments} emails"
            )
        self.signals.result.emit(attachments)

class EmailAttachmentsWindow(FramelessWindowBase):
    """Simple email attachments viewer with FilterTableView"""
    
    def __init__(self, parent=None):
        from suiteview.core.access_control import guard_app_access
        guard_app_access("EMAILATTACHMENTS")
        self.outlook = None  # Lazy-load Outlook only when needed
        self.repo = get_email_repository()
        self.attachment_data = None
        self._scan_days = 14  # Default scan period
        
        # Load saved scan period from database
        saved_period = self.repo.get_setting('attachment_scan_days', '14')
        try:
            self._scan_days = int(saved_period)
        except (TypeError, ValueError):
            logger.debug("Invalid saved attachment scan period %r; using default", saved_period, exc_info=True)
            self._scan_days = 14
        
        self._loader_worker = None
        self._loader_controller = None

        FramelessWindowBase.__init__(
            self,
            title="📎 EMAIL ATTACHMENTS",
            default_size=(1200, 600),
            min_size=(400, 300),
            parent=parent,
            header_colors=("#1E5BA8", "#0D3A7A", "#082B5C"),
            border_color="#D4A017",
            header_title_stretch=1,
        )
        self.setWindowTitle("SuiteView - Email Attachments")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Load from cache immediately - no delay needed since it's fast (~30ms)
        self.load_from_cache_only()
        
        # Bring window to front
        self.raise_()
        self.activateWindow()
        
        logger.info("Email Attachments Window initialized")
    
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
        # Update button - gets new attachments since last cached
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setFixedSize(28, 28)
        self.refresh_btn.setToolTip("Update - check for new attachments since last scan")
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
        return [self.refresh_btn]

    def build_content(self):
        return self.init_ui()

    def init_ui(self):
        """Initialize the UI with SuiteView theme"""
        body = QWidget()
        main_layout = QVBoxLayout(body)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

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
                font-family: "Segoe UI", Tahoma, Geneva, sans-serif;
                font-size: 10px;
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
                font-family: "Segoe UI", Tahoma, Geneva, sans-serif;
                font-weight: bold;
                font-size: 10px;
            }
        """)
        # Hide the row index (vertical header)
        if hasattr(self.attachments_grid, 'table_view'):
            self.attachments_grid.table_view.verticalHeader().setVisible(False)
            self.attachments_grid.table_view.setShowGrid(False)
            self.attachments_grid.table_view.setAlternatingRowColors(False)
            # Set file icon delegate for the Attachment column (column 7)
            self.file_icon_delegate = FileIconDelegate(self.attachments_grid.table_view)
            self.attachments_grid.table_view.setItemDelegateForColumn(7, self.file_icon_delegate)
        content_layout.addWidget(self.attachments_grid)
        
        # Connect double-click handler
        if hasattr(self.attachments_grid, 'table_view'):
            self.attachments_grid.table_view.doubleClicked.connect(self.on_double_click)
            # Append our own actions to the grid's built-in right-click menu
            self.attachments_grid.context_menu_hook = self._add_attachment_menu_actions
        
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
        
        main_layout.addWidget(footer)
        return body
    
    def _on_rescan_clicked(self):
        """Handle rescan button click - clear cache and reload fresh"""
        # Get selected period
        days = self.period_combo.currentData()
        self._scan_days = days
        
        # Save to database
        self.repo.set_setting('attachment_scan_days', str(days))
        
        # Clear cache before rescanning to ensure fresh data with current filters
        try:
            self.repo.clear_cache()
            logger.info("Cache cleared before rescan")
        except Exception as e:
            logger.warning(f"Could not clear cache before rescan: {e}")
        
        # Reload attachments with new period (force full scan)
        self.load_attachments(force_full_scan=True)
    
    def _on_stop_clicked(self):
        """Handle stop button click - stop the scan and show results so far"""
        if self._loader_controller and self._loader_controller.is_running():
            self.status_label.setText("Stopping scan...")
            self._loader_controller.cancel()
            self.stop_btn.setEnabled(False)
    
    def load_from_cache_only(self):
        """Load attachments from cache only - no Outlook scanning"""
        # Calculate the date range for the requested period
        requested_start = datetime.now() - timedelta(days=self._scan_days)
        
        self.status_label.setText("Loading from cache...")
        
        try:
            cached_attachments = self.repo.get_attachments_since(requested_start)
            
            if not cached_attachments:
                self.status_label.setText("No cached data. Click 'Update' or 'Re-scan' to scan emails.")
                return
            
            # Convert cached attachments to standard format
            all_attachments = self._convert_cached_attachments(cached_attachments)
            
            # Convert to DataFrame and process
            df = pd.DataFrame(all_attachments)
            display_df, df = _process_attachment_dataframe(df)
            
            if display_df is None:
                period_text = self._get_period_text()
                self.status_label.setText(f"No file attachments in cache ({period_text}). Click 'Update' or 'Re-scan' to scan emails.")
                return
            
            # Store original data for lookups
            self.attachment_data = df
            
            # Load into grid
            self.attachments_grid.set_dataframe(display_df)
            self._configure_grid_columns()
            
            period_text = self._get_period_text()
            self.status_label.setText(f"Loaded {len(df)} attachments from cache ({period_text})")
            
        except Exception as e:
            logger.error(f"Error loading from cache: {e}", exc_info=True)
            self.status_label.setText(f"Error loading cache: {str(e)}")

    
    def load_attachments(self, force_full_scan=False):
        """Load recent attachments - uses cache when possible"""
        # Lazy-initialize Outlook connection only when needed
        if self.outlook is None:
            self.outlook = get_outlook_manager()
        
        # Disable buttons during load
        self.refresh_btn.setEnabled(False)
        self.rescan_btn.setEnabled(False)
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
        
        # Start background worker for new emails
        self._loader_worker = AttachmentLoaderWorker(
            days=self._scan_days, 
            scan_from_date=scan_from_date,
        )
        self._loader_controller = WorkerController(
            self,
            self._loader_worker,
            cancel=self._loader_worker.cancel,
        )
        self._loader_controller.progress.connect(self._on_load_progress)
        self._loader_controller.result.connect(
            lambda new_attach: self._on_load_finished(new_attach, "", cached_attachments)
        )
        self._loader_controller.error.connect(
            lambda err: self._on_load_finished([], str(err), cached_attachments)
        )
        self._loader_controller.finished.connect(self._on_loader_finished)
        self._loader_controller.start()
    
    def _on_attachment_found(self, attachment):
        """Cache individual attachment as it's found"""
        try:
            self.repo.save_attachment_simple(attachment)
        except Exception as e:
            logger.debug(f"Failed to cache attachment: {e}")
    
    def _on_load_progress(self, payload):
        """Update status during background load"""
        if isinstance(payload, dict) and payload.get("kind") == "attachment":
            self._on_attachment_found(payload["attachment"])
            return
        if isinstance(payload, dict):
            message = payload.get("message", "")
        else:
            message = str(payload)
        self.status_label.setText(message)

    def _on_loader_finished(self):
        self._loader_worker = None
        self._loader_controller = None
    
    @staticmethod
    def _convert_cached_attachments(cached_attachments):
        """Convert cached DB-format attachments to standard dict format"""
        result = []
        for cached in cached_attachments:
            cached_date = cached.get('email_date')
            if cached_date:
                if isinstance(cached_date, str):
                    try:
                        cached_date = datetime.fromisoformat(cached_date)
                    except ValueError:
                        logger.debug("Invalid cached email attachment date %r; using current time", cached_date, exc_info=True)
                        cached_date = datetime.now()
            else:
                cached_date = datetime.now()
            
            result.append({
                'sender': cached['email_sender'],
                'sender_name': cached.get('sender_name', ''),
                'email_subject': cached.get('email_subject', ''),
                'date': cached_date,
                'attachment_name': cached['attachment_name'],
                'attachment_size': cached.get('attachment_size', 0),
                'email_id': cached['email_id'],
                'attachment_index': cached['attachment_index']
            })
        return result
    
    def _on_load_finished(self, new_attachments, error, cached_attachments=None):
        """Handle completion of background load"""
        self.refresh_btn.setEnabled(True)
        self.rescan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)  # Disable stop button when scan complete
        
        if error:
            self.status_label.setText(error)
            return
        
        # Combine cached and new attachments
        cached_attachments = cached_attachments or []
        
        # Start with new attachments
        all_attachments = list(new_attachments)
        
        # Add cached attachments, skipping duplicates
        for cached in cached_attachments:
            is_duplicate = any(
                a['email_id'] == cached['email_id'] and 
                a['attachment_index'] == cached['attachment_index']
                for a in new_attachments
            )
            if not is_duplicate:
                all_attachments.extend(self._convert_cached_attachments([cached]))
        
        if not all_attachments:
            period_text = self._get_period_text()
            self.status_label.setText(f"No attachments found in the {period_text}")
            return
        
        try:
            df = pd.DataFrame(all_attachments)
            display_df, df = _process_attachment_dataframe(df)
            
            if display_df is None:
                period_text = self._get_period_text()
                self.status_label.setText(f"No file attachments found in the {period_text} (images excluded)")
                return
            
            # Store original data for lookups
            self.attachment_data = df
            
            # Load into grid
            self.attachments_grid.set_dataframe(display_df)
            self._configure_grid_columns()
            
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
    
    def _configure_grid_columns(self):
        """Set column widths and alignment after loading data"""
        # Columns: Full Name(0), Sender(1), Domain(2), Sent Date(3), Subject(4), Type(5), Size(6), Attachment(7)
        if hasattr(self.attachments_grid, 'model') and self.attachments_grid.model:
            self.attachments_grid.model._left_align_columns = {0, 4, 7}  # Full Name, Subject, Attachment
        if hasattr(self.attachments_grid, 'table_view'):
            self.attachments_grid.table_view.setColumnWidth(4, 300)  # Subject

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
        
        # Column 7 is Attachment - open attachment
        # Other columns - open email
        if col == 7:
            self.open_attachment(email_id, attachment_index)
        else:
            self.open_email(email_id)
    
    def open_email(self, email_id: str):
        """Open email in Outlook"""
        # Lazy-initialize Outlook connection only when needed
        if self.outlook is None:
            self.outlook = get_outlook_manager()
        
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
        # Lazy-initialize Outlook connection only when needed
        if self.outlook is None:
            self.outlook = get_outlook_manager()
        
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

    def _attachment_at_row(self, row: int):
        """Resolve the attachment record for a view row (handles filtering)."""
        if self.attachment_data is None or self.attachment_data.empty:
            return None
        if hasattr(self.attachments_grid, 'model') and self.attachments_grid.model:
            display_indices = self.attachments_grid.model._display_indices
            if row < 0 or row >= len(display_indices):
                return None
            return self.attachment_data.loc[display_indices[row]]
        if row < 0 or row >= len(self.attachment_data):
            return None
        return self.attachment_data.iloc[row]

    def _add_attachment_menu_actions(self, menu, index):
        """Hook: append attachment actions to the grid's built-in context menu."""
        attachment = self._attachment_at_row(index.row())
        if attachment is None:
            return
        email_id = attachment['email_id']
        attachment_index = attachment['attachment_index']

        menu.addSeparator()
        open_action = menu.addAction("📎 Open Attachment")
        open_action.triggered.connect(
            lambda: self.open_attachment(email_id, attachment_index))
        copy_action = menu.addAction("📋 Copy File to Clipboard")
        copy_action.triggered.connect(
            lambda: self.copy_attachment_to_clipboard(email_id, attachment_index))
        open_email_action = menu.addAction("✉ Open Email")
        open_email_action.triggered.connect(lambda: self.open_email(email_id))

    def copy_attachment_to_clipboard(self, email_id: str, attachment_index: int):
        """Copy the attachment file to the clipboard so it can be pasted (Ctrl+V)
        into a folder or another application."""
        # Lazy-initialize Outlook connection only when needed
        if self.outlook is None:
            self.outlook = get_outlook_manager()

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

            if not temp_path or not os.path.exists(temp_path):
                QMessageBox.warning(self, "Error", "Failed to retrieve attachment")
                return

            mime_data = QMimeData()
            mime_data.setUrls([QUrl.fromLocalFile(temp_path)])
            QApplication.clipboard().setMimeData(mime_data)

            self.status_label.setText(
                f"Copied '{os.path.basename(temp_path)}' to clipboard — "
                "Ctrl+V to paste")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Error", f"Failed to copy attachment: {e}")
    
