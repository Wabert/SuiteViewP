"""
Outlook Manager - Integration with Microsoft Outlook via COM

Provides access to Outlook emails, folders, and attachments for the Email Navigator feature.
Uses win32com for COM integration with Outlook application.
"""

import logging
import os
import hashlib
import threading
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from suiteview.core.access_control import AccessDeniedError, AccessUnavailableError
from suiteview.core.support_files import guard_support_file_paths

logger = logging.getLogger(__name__)

try:
    from pywintypes import com_error as OutlookComError
except ImportError:
    OutlookComError = None

OUTLOOK_COM_ERRORS = (AttributeError, TypeError, OSError) + (
    (OutlookComError,) if OutlookComError is not None else ()
)


@dataclass
class EmailAttachment:
    """Email attachment information"""
    email_id: str
    email_subject: str
    email_sender: str
    email_date: datetime
    attachment_name: str
    attachment_type: str  # File extension
    attachment_size: int  # Bytes
    attachment_index: int  # Index in email's attachments collection
    file_hash: Optional[str] = None  # For duplicate detection


@dataclass
class EmailInfo:
    """Email information"""
    email_id: str
    subject: str
    sender: str
    sender_email: str
    received_date: datetime
    size: int
    unread: bool
    has_attachments: bool
    attachment_count: int
    folder_path: str
    body_preview: str  # First 200 chars


class OutlookManager:
    """Manager for Outlook integration via win32com"""
    
    def __init__(self):
        """Initialize Outlook connection"""
        self.outlook = None
        self.namespace = None
        self.connected = False
        self._com_initialized = False
        self._initialize_outlook()
    
    def _initialize_outlook(self):
        """Initialize connection to Outlook with retry logic"""
        try:
            import win32com.client
            import pythoncom
            import time
            
            # Try to connect with retries
            max_retries = 3
            retry_delay = 2  # seconds
            
            for attempt in range(max_retries):
                try:
                    # Initialize COM for this thread
                    pythoncom.CoInitialize()
                    self._com_initialized = True
                    
                    # Try to get existing instance first, fall back to creating new one
                    try:
                        self.outlook = win32com.client.GetActiveObject("Outlook.Application")
                        logger.info("Connected to existing Outlook instance")
                    except OUTLOOK_COM_ERRORS:
                        logger.info("Starting new Outlook instance...")
                        self.outlook = win32com.client.Dispatch("Outlook.Application")
                        # Give Outlook time to fully start
                        time.sleep(2)
                    
                    self.namespace = self.outlook.GetNamespace("MAPI")
                    
                    # Verify connection by accessing a folder
                    _ = self.namespace.Folders.Count
                    
                    self.connected = True
                    logger.info("Successfully connected to Outlook")
                    return
                    
                except Exception as e:
                    logger.warning(f"Outlook connection attempt {attempt + 1}/{max_retries} failed: {e}")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                    else:
                        raise
                        
        except ImportError as e:
            logger.error("pywin32 not installed. Install with: pip install pywin32")
            logger.error(f"Import error details: {e}")
            self.connected = False
        except Exception as e:
            logger.error(f"Failed to connect to Outlook after {max_retries} attempts: {e}")
            logger.error("Please ensure Outlook is installed and you have permission to access it.")
            logger.error("Try manually starting Outlook and then restart this application.")
            self.connected = False
    
    def is_connected(self) -> bool:
        """Check if connected to Outlook"""
        if self.connected:
            return self.verify_connection()
        return False

    def verify_connection(self) -> bool:
        """Verify the COM connection is still alive, auto-reconnect if stale"""
        try:
            _ = self.namespace.Folders.Count
            return True
        except Exception:
            logger.warning("Outlook COM connection is stale, attempting reconnect...")
            self.connected = False
            self._initialize_outlook()
            return self.connected

    def close(self):
        """Release COM resources and uninitialize COM for this thread"""
        try:
            self.outlook = None
            self.namespace = None
            self.connected = False
            if self._com_initialized:
                import pythoncom
                pythoncom.CoUninitialize()
                self._com_initialized = False
                logger.debug("COM uninitialized for thread")
        except Exception as e:
            logger.debug(f"Error during OutlookManager cleanup: {e}")
    
    def reconnect(self) -> bool:
        """Attempt to reconnect to Outlook
        
        Returns:
            True if reconnection successful, False otherwise
        """
        logger.info("Attempting to reconnect to Outlook...")
        self.connected = False
        self.outlook = None
        self.namespace = None
        self._initialize_outlook()
        return self.connected
    
    def get_folder_tree(self) -> List[Dict]:
        """Get all mail folders as a tree structure"""
        if not self.connected:
            return []
        
        try:
            folders = []
            
            # Get all accounts
            for store in self.namespace.Stores:
                store_info = {
                    'name': store.DisplayName,
                    'type': 'store',
                    'path': store.DisplayName,
                    'children': []
                }
                
                # Get root folder
                try:
                    root_folder = store.GetRootFolder()
                    self._add_folder_tree(root_folder, store_info['children'], store.DisplayName)
                except Exception as e:
                    logger.warning(f"Could not access store {store.DisplayName}: {e}")
                
                folders.append(store_info)
            
            return folders
        except Exception as e:
            logger.error(f"Error getting folder tree: {e}")
            return []
    
    def _add_folder_tree(self, folder, parent_list: List, parent_path: str):
        """Recursively build folder tree"""
        try:
            folder_info = {
                'name': folder.Name,
                'type': 'folder',
                'path': f"{parent_path}/{folder.Name}",
                'item_count': folder.Items.Count,
                'unread_count': folder.UnReadItemCount,
                'children': []
            }
            
            # Recursively add subfolders
            for subfolder in folder.Folders:
                self._add_folder_tree(subfolder, folder_info['children'], folder_info['path'])
            
            parent_list.append(folder_info)
        except Exception as e:
            logger.warning(f"Error processing folder: {e}")
    
    def get_inbox_folder(self):
        """Get the Inbox folder"""
        if not self.connected:
            logger.error("Not connected to Outlook")
            return None
        
        try:
            # Try multiple approaches to get Inbox
            
            # Approach 1: Use GetDefaultFolder with constant
            logger.info("Attempting to access Inbox via GetDefaultFolder...")
            try:
                inbox = self.namespace.GetDefaultFolder(6)  # 6 = olFolderInbox
                if inbox:
                    logger.info(f"Successfully accessed Inbox: {inbox.Name}")
                    return inbox
            except Exception as e1:
                logger.warning(f"GetDefaultFolder failed: {e1}")
            
            # Approach 2: Navigate through Folders collection
            logger.info("Attempting to access Inbox via Folders collection...")
            try:
                folders = self.namespace.Folders
                logger.info(f"Found {folders.Count} folder(s) in namespace")
                if folders and folders.Count > 0:
                    # Try first store
                    store = folders.Item(1)
                    logger.info(f"Accessing first store: {store.Name}")
                    # Try to get Inbox folder by name
                    for folder in store.Folders:
                        logger.debug(f"Found folder: {folder.Name}")
                        if folder.Name.lower() in ['inbox', 'posteingang', 'boîte de réception']:
                            logger.info(f"Found Inbox folder: {folder.Name}")
                            return folder
            except Exception as e2:
                logger.warning(f"Folders collection navigation failed: {e2}")
            
            # Approach 3: Use default delivery location
            logger.info("Attempting to access Inbox via DefaultStore...")
            try:
                default_store = self.namespace.DefaultStore
                if default_store:
                    logger.info(f"Default store: {default_store.DisplayName}")
                    root = default_store.GetRootFolder()
                    logger.info(f"Root folder: {root.Name}")
                    for folder in root.Folders:
                        logger.debug(f"Found folder: {folder.Name}")
                        if folder.Name.lower() in ['inbox', 'posteingang', 'boîte de réception']:
                            logger.info(f"Found Inbox folder: {folder.Name}")
                            return folder
            except Exception as e3:
                logger.warning(f"DefaultStore navigation failed: {e3}")
            
            logger.error("Could not access Inbox through any method")
            return None
            
        except Exception as e:
            logger.error(f"Error getting Inbox folder: {e}", exc_info=True)
            return None
    
    def get_folder_by_path(self, path: str):
        """Get folder by path (e.g., 'Account/Inbox/Subfolder')"""
        if not self.connected:
            return None
        
        try:
            parts = path.split('/')
            if len(parts) < 2:
                return None
            
            # Find the store
            store_name = parts[0]
            store = None
            for s in self.namespace.Stores:
                if s.DisplayName == store_name:
                    store = s
                    break
            
            if not store:
                return None
            
            # Navigate to the folder
            folder = store.GetRootFolder()
            for part in parts[1:]:
                found = False
                for subfolder in folder.Folders:
                    if subfolder.Name == part:
                        folder = subfolder
                        found = True
                        break
                if not found:
                    return None
            
            return folder
        except Exception as e:
            logger.error(f"Error getting folder by path '{path}': {e}")
            return None
    
    def get_emails(self, folder=None, limit: int = 1000, include_body_preview: bool = False) -> List[EmailInfo]:
        """Get emails from a folder
        
        Args:
            folder: Folder object or None for Inbox
            limit: Maximum number of emails to retrieve (most recent)
            include_body_preview: Whether to include body preview (slower)
        
        Returns:
            List of EmailInfo objects
        """
        if not self.connected:
            return []
        
        try:
            if folder is None:
                folder = self.get_inbox_folder()
            
            if folder is None:
                return []
            
            emails = []
            items = folder.Items
            items.Sort("[ReceivedTime]", True)  # Sort by received time, descending
            
            count = 0
            for item in items:
                if count >= limit:
                    break
                
                try:
                    # Only process MailItem objects
                    if item.Class != 43:  # 43 = olMail
                        continue
                    
                    # Get sender email
                    try:
                        sender_email = item.SenderEmailAddress
                        # Handle Exchange addresses (internal emails)
                        # Only convert /O= addresses, keep regular SMTP addresses as-is
                        if sender_email and sender_email.startswith('/O='):
                            try:
                                sender_email = item.Sender.GetExchangeUser().PrimarySmtpAddress
                            except OUTLOOK_COM_ERRORS:
                                # If GetExchangeUser fails, fall back to SenderName
                                logger.debug("Could not resolve Exchange sender address; using SenderName", exc_info=True)
                                sender_email = item.SenderName
                        # For external emails, sender_email should already be the SMTP address
                    except OUTLOOK_COM_ERRORS:
                        logger.debug("Could not read Outlook sender email address", exc_info=True)
                        sender_email = ""
                    
                    # Get body preview
                    body_preview = ""
                    if include_body_preview:
                        try:
                            body = item.Body or ""
                            body_preview = body[:200].replace('\r', ' ').replace('\n', ' ')
                        except OUTLOOK_COM_ERRORS:
                            logger.debug("Could not read Outlook body preview", exc_info=True)
                            body_preview = ""
                    
                    email_info = EmailInfo(
                        email_id=item.EntryID,
                        subject=item.Subject or "(No Subject)",
                        sender=item.SenderName or "(Unknown)",
                        sender_email=sender_email,
                        received_date=item.ReceivedTime,
                        size=item.Size,
                        unread=item.UnRead,
                        has_attachments=item.Attachments.Count > 0,
                        attachment_count=item.Attachments.Count,
                        folder_path=self._get_folder_path(folder),
                        body_preview=body_preview
                    )
                    
                    emails.append(email_info)
                    count += 1
                
                except Exception as e:
                    logger.warning(f"Error processing email: {e}")
                    continue
            
            return emails
        
        except Exception as e:
            logger.error(f"Error getting emails: {e}")
            return []
    
    def _is_inline_attachment(self, attachment) -> bool:
        """Check if attachment is inline/embedded (not a true file attachment)
        
        This uses PR_ATTACHMENT_HIDDEN which is what Outlook uses to determine
        whether to show the paperclip icon. If Hidden=True, the attachment is
        inline/embedded. If Hidden=False, it appears in the attachment bar.
        
        Args:
            attachment: Outlook attachment object
            
        Returns:
            True if inline/embedded (hidden), False if true file attachment (visible)
        """
        try:
            # Check PR_ATTACHMENT_HIDDEN - this is what Outlook uses for the paperclip icon
            try:
                pr_attach_hidden = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"
                is_hidden = attachment.PropertyAccessor.GetProperty(pr_attach_hidden)
                return bool(is_hidden)
            except OUTLOOK_COM_ERRORS:
                logger.debug("Could not read Outlook inline attachment property; assuming visible", exc_info=True)
                return False  # If we can't read it, assume not hidden (visible)
            
        except Exception as e:
            logger.warning(f"Error checking if inline attachment: {e}")
            return False
    
    def _get_folder_path(self, folder) -> str:
        """Get full path of a folder"""
        try:
            path_parts = []
            current = folder
            
            while current:
                try:
                    path_parts.insert(0, current.Name)
                    current = current.Parent
                    # Stop at store level
                    if hasattr(current, 'Class') and current.Class == 61:  # olStore
                        break
                except OUTLOOK_COM_ERRORS:
                    logger.debug("Stopped building folder path because an Outlook parent/name could not be read", exc_info=True)
                    break
            
            return '/'.join(path_parts)
        except OUTLOOK_COM_ERRORS:
            logger.debug("Could not build Outlook folder path", exc_info=True)
            return "Unknown"

    def _sender_info(self, item, fallback=None, context: str = "") -> tuple[str, str]:
        """Best-effort Outlook sender display name and SMTP address."""
        sender_email = ""
        sender_name = ""
        try:
            sender_name = self._sender_name(item, context)
            sender_email = self._sender_email(item, context)
            if not sender_name:
                sender_name = self._sender_object_name(item, context)
            if fallback is not None:
                sender_name = sender_name or str(getattr(fallback, 'sender', '') or '').strip()
                sender_email = sender_email or str(getattr(fallback, 'sender_email', '') or '').strip()
        except Exception as e:
            logger.warning(f"Sender extraction failed for {getattr(item, 'Subject', '')}: {e}")
        return sender_name or sender_email or "(Unknown Sender)", sender_email

    @staticmethod
    def _sender_name(item, context: str) -> str:
        try:
            raw_sender_name = item.SenderName
            return str(raw_sender_name).strip() if raw_sender_name is not None else ""
        except OUTLOOK_COM_ERRORS:
            logger.debug(f"Could not read Outlook SenderName{context}", exc_info=True)
            return ""

    @staticmethod
    def _sender_email(item, context: str) -> str:
        try:
            raw_sender_email = item.SenderEmailAddress
            sender_email = str(raw_sender_email).strip() if raw_sender_email is not None else ""
            if sender_email and sender_email.startswith('/O='):
                return OutlookManager._exchange_sender_email(item, context) or sender_email
            return sender_email
        except OUTLOOK_COM_ERRORS:
            logger.debug(f"Could not read Outlook SenderEmailAddress{context}", exc_info=True)
            return ""

    @staticmethod
    def _exchange_sender_email(item, context: str) -> str:
        try:
            if item.Sender:
                exchange_user = item.Sender.GetExchangeUser()
                if exchange_user and exchange_user.PrimarySmtpAddress:
                    return str(exchange_user.PrimarySmtpAddress).strip()
        except OUTLOOK_COM_ERRORS:
            logger.debug(f"Could not resolve Exchange sender{context}", exc_info=True)
        return ""

    @staticmethod
    def _sender_object_name(item, context: str) -> str:
        try:
            if item.Sender and item.Sender.Name:
                return str(item.Sender.Name).strip()
        except OUTLOOK_COM_ERRORS:
            logger.debug(f"Could not read Outlook Sender.Name{context}", exc_info=True)
        return ""

    def _email_attachments_from_item(
        self,
        item,
        calculate_hash: bool,
        fallback=None,
        context: str = "",
    ) -> List[EmailAttachment]:
        display_sender, sender_email = self._sender_info(item, fallback, context)
        attachments: List[EmailAttachment] = []
        for idx, attachment in enumerate(item.Attachments, 1):
            try:
                info = self._attachment_info(item, attachment, idx, calculate_hash, display_sender, sender_email)
                if info is not None:
                    attachments.append(info)
            except Exception as e:
                logger.warning(f"Error processing attachment {idx}: {e}")
        return attachments

    def _attachment_info(
        self,
        item,
        attachment,
        index: int,
        calculate_hash: bool,
        display_sender: str,
        sender_email: str,
    ) -> Optional[EmailAttachment]:
        if attachment.Type != 1 or self._is_inline_image(attachment):
            return None
        file_ext = os.path.splitext(attachment.FileName)[1].lower()
        return EmailAttachment(
            email_id=item.EntryID,
            email_subject=item.Subject or "(No Subject)",
            email_sender=sender_email or display_sender,
            email_date=item.ReceivedTime,
            attachment_name=attachment.FileName,
            attachment_type=file_ext or 'unknown',
            attachment_size=attachment.Size,
            attachment_index=index,
            file_hash=self._attachment_hash(attachment) if calculate_hash else None,
        )

    @staticmethod
    def _attachment_hash(attachment) -> Optional[str]:
        try:
            temp_path = os.path.join(os.getenv('TEMP'), attachment.FileName)
            attachment.SaveAsFile(temp_path)
            with open(temp_path, 'rb') as handle:
                file_hash = hashlib.md5(handle.read()).hexdigest()
            os.remove(temp_path)
            return file_hash
        except Exception as e:
            logger.warning(f"Could not calculate hash for {attachment.FileName}: {e}")
            return None
    
    def get_all_attachments(self, folders: List = None, limit_per_folder: int = 1000, 
                           calculate_hash: bool = False) -> List[EmailAttachment]:
        """Get all attachments from specified folders
        
        Args:
            folders: List of folder objects or None for Inbox only
            limit_per_folder: Maximum emails to scan per folder
            calculate_hash: Whether to calculate file hash for duplicate detection
        
        Returns:
            List of EmailAttachment objects
        """
        if not self.connected:
            return []
        
        if folders is None:
            folders = [self.get_inbox_folder()]
        
        all_attachments = []
        
        for folder in folders:
            if folder is None:
                continue
            
            try:
                items = folder.Items
                items.Sort("[ReceivedTime]", True)
                count = 0
                for item in items:
                    if count >= limit_per_folder:
                        break
                    try:
                        if item.Class != 43 or item.Attachments.Count == 0:
                            continue
                        all_attachments.extend(
                            self._email_attachments_from_item(
                                item, calculate_hash, context=" during attachment scan",
                            )
                        )
                        count += 1
                    except Exception as e:
                        logger.warning(f"Error processing email for attachments: {e}")
                        continue
            
            except Exception as e:
                logger.error(f"Error scanning folder for attachments: {e}")
                continue
        
        return all_attachments
    
    def open_email(self, email_id: str) -> bool:
        """Open an email in Outlook
        
        Args:
            email_id: EntryID of the email
        
        Returns:
            True if successful
        """
        if not self.connected:
            return False
        
        try:
            item = self.namespace.GetItemFromID(email_id)
            item.Display()
            return True
        except Exception as e:
            logger.error(f"Error opening email: {e}")
            return False
    
    def save_attachment(self, email_id: str, attachment_index: int, save_path: str) -> bool:
        """Save an attachment to disk
        
        Args:
            email_id: EntryID of the email
            attachment_index: Index of the attachment (1-based)
            save_path: Full path where to save the attachment
        
        Returns:
            True if successful
        """
        if not self.connected:
            return False
        
        try:
            item = self.namespace.GetItemFromID(email_id)
            
            if attachment_index < 1 or attachment_index > item.Attachments.Count:
                logger.error(f"Invalid attachment index: {attachment_index}")
                return False
            
            attachment = item.Attachments.Item(attachment_index)
            
            # Ensure directory exists
            guard_support_file_paths(save_path, action="save policy support attachments")
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            # Handle file name conflicts
            if os.path.exists(save_path):
                base, ext = os.path.splitext(save_path)
                counter = 1
                while os.path.exists(f"{base}_{counter}{ext}"):
                    counter += 1
                save_path = f"{base}_{counter}{ext}"
            
            guard_support_file_paths(save_path, action="save policy support attachments")
            attachment.SaveAsFile(save_path)
            logger.info(f"Saved attachment to: {save_path}")
            return True
        
        except (AccessDeniedError, AccessUnavailableError):
            raise
        except Exception as e:
            logger.error(f"Error saving attachment: {e}")
            return False
    
    def save_multiple_attachments(self, attachments: List[Tuple[str, int]], target_dir: str) -> Dict[str, bool]:
        """Save multiple attachments to a directory
        
        Args:
            attachments: List of (email_id, attachment_index) tuples
            target_dir: Directory to save attachments
        
        Returns:
            Dictionary mapping attachment name to success status
        """
        results = {}
        
        for email_id, attach_idx in attachments:
            try:
                item = self.namespace.GetItemFromID(email_id)
                attachment = item.Attachments.Item(attach_idx)
                
                save_path = os.path.join(target_dir, attachment.FileName)
                success = self.save_attachment(email_id, attach_idx, save_path)
                results[attachment.FileName] = success
            
            except Exception as e:
                logger.error(f"Error in batch save for attachment {attach_idx} from email {email_id}: {e}")
                results[f"attachment_{attach_idx}"] = False
        
        return results
    
    def mark_as_read(self, email_id: str) -> bool:
        """Mark email as read
        
        Args:
            email_id: EntryID of the email
        
        Returns:
            True if successful
        """
        if not self.connected:
            return False
        
        try:
            item = self.namespace.GetItemFromID(email_id)
            item.UnRead = False
            item.Save()
            return True
        except Exception as e:
            logger.error(f"Error marking email as read: {e}")
            return False
    
    def mark_as_unread(self, email_id: str) -> bool:
        """Mark email as unread
        
        Args:
            email_id: EntryID of the email
        
        Returns:
            True if successful
        """
        if not self.connected:
            return False
        
        try:
            item = self.namespace.GetItemFromID(email_id)
            item.UnRead = True
            item.Save()
            return True
        except Exception as e:
            logger.error(f"Error marking email as unread: {e}")
            return False
    
    def get_attachment_preview_path(self, email_id: str, attachment_index: int) -> Optional[str]:
        """Save attachment to temp directory for preview
        
        Args:
            email_id: EntryID of the email
            attachment_index: Index of the attachment
        
        Returns:
            Path to temp file or None
        """
        if not self.connected:
            return None
        
        try:
            item = self.namespace.GetItemFromID(email_id)
            attachment = item.Attachments.Item(attachment_index)
            
            temp_dir = os.path.join(os.getenv('TEMP'), 'SuiteView_Email_Previews')
            temp_path = os.path.join(temp_dir, attachment.FileName)
            guard_support_file_paths(temp_dir, temp_path, action="save policy support attachments")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Only save if not already exists or is old
            if not os.path.exists(temp_path):
                guard_support_file_paths(temp_path, action="save policy support attachments")
                attachment.SaveAsFile(temp_path)
            
            return temp_path
        
        except (AccessDeniedError, AccessUnavailableError):
            raise
        except Exception as e:
            logger.error(f"Error getting attachment preview: {e}")
            return None
    
    def get_emails_since(self, folder, since_date, include_body_preview: bool = False) -> List[EmailInfo]:
        """Get emails received after a specific date (for incremental sync)
        
        Args:
            folder: Outlook folder object
            since_date: Only get emails received after this datetime
            include_body_preview: Whether to include body preview
        
        Returns:
            List of EmailInfo objects
        """
        if not self.connected:
            return []
        
        try:
            items = folder.Items
            items.Sort("[ReceivedTime]", True)  # Sort by received time, descending
            
            # Outlook filter format: [ReceivedTime] > 'mm/dd/yyyy HH:MM AM/PM'
            filter_str = f"[ReceivedTime] > '{since_date.strftime('%m/%d/%Y %I:%M %p')}'"
            logger.info(f"Incremental sync filter: {filter_str}")
            
            filtered_items = items.Restrict(filter_str)
            logger.info(f"Found {filtered_items.Count} emails since {since_date}")
            
            emails = []
            for item in filtered_items:
                try:
                    # Only process MailItem objects
                    if item.Class != 43:  # 43 = olMail
                        continue
                    
                    # Get sender email
                    try:
                        sender_email = item.SenderEmailAddress
                        if sender_email.startswith('/O='):
                            try:
                                sender_email = item.Sender.GetExchangeUser().PrimarySmtpAddress
                            except OUTLOOK_COM_ERRORS:
                                logger.debug("Could not resolve Exchange sender in date-filtered email scan", exc_info=True)
                                sender_email = item.SenderName
                    except OUTLOOK_COM_ERRORS:
                        logger.debug("Could not read Outlook sender in date-filtered email scan", exc_info=True)
                        sender_email = ""
                    
                    # Get body preview
                    body_preview = ""
                    if include_body_preview:
                        try:
                            body = item.Body or ""
                            body_preview = body[:200].replace('\r', ' ').replace('\n', ' ')
                        except OUTLOOK_COM_ERRORS:
                            logger.debug("Could not read Outlook body preview in date-filtered email scan", exc_info=True)
                            body_preview = ""
                    
                    email_info = EmailInfo(
                        email_id=item.EntryID,
                        subject=item.Subject or "(No Subject)",
                        sender=item.SenderName or "(Unknown)",
                        sender_email=sender_email,
                        received_date=item.ReceivedTime,
                        size=item.Size,
                        unread=item.UnRead,
                        has_attachments=item.Attachments.Count > 0,
                        attachment_count=item.Attachments.Count,
                        folder_path=self._get_folder_path(folder),
                        body_preview=body_preview
                    )
                    
                    emails.append(email_info)
                
                except Exception as e:
                    logger.warning(f"Error processing email: {e}")
                    continue
            
            logger.info(f"Retrieved {len(emails)} new emails")
            return emails
        
        except Exception as e:
            logger.error(f"Error getting emails since {since_date}: {e}")
            return []
    
    def get_attachments_from_emails(self, emails: List[EmailInfo], calculate_hash: bool = False) -> List[EmailAttachment]:
        """Get attachments from a specific list of email objects
        
        Args:
            emails: List of EmailInfo objects to scan for attachments
            calculate_hash: Whether to calculate MD5 hash (slower)
        
        Returns:
            List of EmailAttachment objects
        """
        if not self.connected:
            return []
        
        attachments = []
        
        for email in emails:
            if not email.has_attachments:
                continue
            
            try:
                item = self.namespace.GetItemFromID(email.email_id)
                attachments.extend(
                    self._email_attachments_from_item(
                        item, calculate_hash, fallback=email,
                        context=" while scanning attachments",
                    )
                )
            except Exception as e:
                logger.warning(f"Error accessing email attachments: {e}")
                continue
        
        logger.info(f"Found {len(attachments)} attachments from {len(emails)} emails")
        return attachments

    # ── Task Tracker helpers ────────────────────────────────────────

    def get_contacts(self) -> List[Dict]:
        """Retrieve contacts from Outlook Contacts folder and GAL.

        Returns a list of dicts: [{'name': str, 'email': str}, ...]
        """
        if not self.connected:
            logger.warning("Not connected to Outlook – cannot fetch contacts")
            return []

        contacts: List[Dict] = []
        seen_emails = set()
        self._load_contact_folder_contacts(contacts, seen_emails)
        self._load_gal_contacts(contacts, seen_emails)
        return contacts

    def _add_contact(self, contacts: List[Dict], seen_emails: set, name: str, email: str) -> None:
        email = (email or "").strip()
        if email and email not in seen_emails:
            contacts.append({'name': (name or "").strip(), 'email': email})
            seen_emails.add(email)

    def _load_contact_folder_contacts(self, contacts: List[Dict], seen_emails: set) -> None:
        try:
            contacts_folder = self.namespace.GetDefaultFolder(10)
            for item in contacts_folder.Items:
                try:
                    name = item.FullName or item.Subject or ""
                    email = (getattr(item, 'Email1Address', '') or "").strip()
                    self._add_contact(contacts, seen_emails, name, email)
                except Exception:
                    logger.debug("Skipping unreadable Outlook contact", exc_info=True)
                    continue
            logger.info(f"Loaded {len(contacts)} contacts from Contacts folder")
        except Exception as e:
            logger.warning(f"Could not access Contacts folder: {e}")

    def _load_gal_contacts(self, contacts: List[Dict], seen_emails: set) -> None:
        try:
            for addr_list in self.namespace.AddressLists:
                if addr_list.Name == "Global Address List":
                    self._load_gal_entries(addr_list, contacts, seen_emails)
                    logger.info(f"Total contacts after GAL: {len(contacts)}")
                    break
        except Exception as e:
            logger.warning(f"Could not access GAL: {e}")

    def _load_gal_entries(self, addr_list, contacts: List[Dict], seen_emails: set) -> None:
        for entry in addr_list.AddressEntries:
            try:
                self._add_contact(contacts, seen_emails, entry.Name or "", self._gal_entry_email(entry))
            except Exception:
                logger.debug("Skipping unreadable Outlook GAL entry", exc_info=True)
                continue

    @staticmethod
    def _gal_entry_email(entry) -> str:
        try:
            exch = entry.GetExchangeUser()
            if exch:
                return exch.PrimarySmtpAddress or ""
        except Exception:
            return entry.Address or ""
        return entry.Address or ""

    def search_contacts(self, query: str) -> List[Dict]:
        """Return contacts whose name or email contains *query* (case-insensitive)."""
        q = query.lower()
        return [
            c for c in self.get_contacts()
            if q in c['name'].lower() or q in c['email'].lower()
        ]

    def send_email(self, to_email: str, subject: str, html_body: str,
                   attachments: List[str] = None) -> bool:
        """Create and send an HTML email via Outlook.

        Args:
            to_email: Recipient email address
            subject: Email subject line
            html_body: HTML content for the email body
            attachments: Optional list of file paths to attach

        Returns:
            True on success, False on failure
        """
        if not self.connected:
            logger.error("Not connected to Outlook – cannot send email")
            return False

        try:
            mail = self.outlook.CreateItem(0)  # 0 = olMailItem
            mail.To = to_email
            mail.Subject = subject
            mail.HTMLBody = html_body

            if attachments:
                for file_path in attachments:
                    if os.path.isfile(file_path):
                        mail.Attachments.Add(file_path)
                    else:
                        logger.warning(f"Attachment not found, skipping: {file_path}")

            mail.Send()
            logger.info(f"Email sent to {to_email}: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    def scan_for_task_replies(self, task_ids: List[str],
                             known_entry_ids: set = None) -> List[EmailInfo]:
        """Scan Inbox + Sent Items for emails matching any [TSK-XXX] pattern.

        Args:
            task_ids: List of task ID strings, e.g. ["TSK-001", "TSK-003"].
            known_entry_ids: Set of Outlook EntryIDs already stored — these
                are skipped to avoid duplicates.

        Returns:
            List of *new* EmailInfo objects not already in *known_entry_ids*.
        """
        if not task_ids:
            return []
        known = known_entry_ids or set()
        all_results: List[EmailInfo] = []
        for tid in task_ids:
            try:
                emails = self.search_emails_by_subject(
                    f"[{tid}]", include_body_preview=True,
                )
                for e in emails:
                    if e.email_id not in known:
                        all_results.append(e)
            except Exception as exc:
                logger.warning(f"scan_for_task_replies — error scanning {tid}: {exc}")
        # Deduplicate by entry_id (a task_id search may overlap)
        seen = set()
        unique: List[EmailInfo] = []
        for e in all_results:
            if e.email_id not in seen:
                seen.add(e.email_id)
                unique.append(e)
        unique.sort(key=lambda e: e.received_date, reverse=True)
        return unique

    def send_task_email(self, to_emails: List[str], subject: str,
                        body: str) -> bool:
        """Send a plain-text task email ensuring [TSK-XXX] is in the subject.

        Args:
            to_emails: List of recipient email addresses.
            subject: Subject line (should already contain [TSK-XXX]).
            body: Plain-text email body.

        Returns:
            True on success, False on failure.
        """
        if not self.connected:
            logger.error("Not connected to Outlook – cannot send task email")
            return False
        try:
            mail = self.outlook.CreateItem(0)
            mail.To = "; ".join(to_emails)
            mail.Subject = subject
            mail.Body = body
            mail.Send()
            logger.info(f"Task email sent to {', '.join(to_emails)}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send task email: {e}")
            return False

    def search_emails_by_subject(self, subject_query: str,
                                  folder=None,
                                  include_body_preview: bool = True) -> List[EmailInfo]:
        """Search for emails whose subject contains *subject_query*.

        Uses Outlook Restrict() for performance.  Searches Inbox by default.
        """
        if not self.connected:
            return []

        try:
            if folder is None:
                folder = self.get_inbox_folder()
            if folder is None:
                logger.error("Could not access Inbox for email search")
                return []

            # Build DASL filter for subject containing the query
            escaped = subject_query.replace("'", "''")
            restriction = (
                f"@SQL=\"urn:schemas:httpmail:subject\" LIKE '%{escaped}%'"
            )

            items = folder.Items
            items.Sort("[ReceivedTime]", True)  # newest first
            restricted = items.Restrict(restriction)

            results = self._search_restricted_items(restricted, folder, include_body_preview)
            results.extend(self._search_sent_items(restriction, include_body_preview))

            # Sort all results by date
            results.sort(key=lambda e: e.received_date, reverse=True)
            logger.info(f"Found {len(results)} emails matching '{subject_query}'")
            return results

        except Exception as e:
            logger.error(f"Email subject search failed: {e}")
            return []

    def _search_restricted_items(self, restricted, folder, include_body_preview: bool) -> List[EmailInfo]:
        results: List[EmailInfo] = []
        for item in restricted:
            try:
                info = self._email_info_from_search_item(item, folder, include_body_preview)
                if info is not None:
                    results.append(info)
            except Exception as e:
                logger.warning(f"Error reading search result: {e}")
        return results

    def _email_info_from_search_item(self, item, folder, include_body_preview: bool) -> Optional[EmailInfo]:
        if getattr(item, 'Class', 0) != 43:
            return None
        return EmailInfo(
            email_id=item.EntryID,
            subject=item.Subject or "(No Subject)",
            sender=item.SenderName or "Unknown",
            sender_email=self._search_sender_email(item),
            received_date=item.ReceivedTime,
            size=item.Size,
            unread=item.UnRead,
            has_attachments=item.Attachments.Count > 0,
            attachment_count=item.Attachments.Count,
            folder_path=folder.FolderPath,
            body_preview=self._body_preview(item, include_body_preview, "subject search result"),
        )

    def _search_sent_items(self, restriction: str, include_body_preview: bool) -> List[EmailInfo]:
        try:
            sent_folder = self.namespace.GetDefaultFolder(5)
            sent_items = sent_folder.Items
            sent_items.Sort("[SentOn]", True)
            return self._sent_search_infos(sent_items.Restrict(restriction), sent_folder, include_body_preview)
        except Exception as e:
            logger.warning(f"Could not search Sent Items: {e}")
            return []

    def _sent_search_infos(self, restricted, sent_folder, include_body_preview: bool) -> List[EmailInfo]:
        results: List[EmailInfo] = []
        for item in restricted:
            try:
                if getattr(item, 'Class', 0) != 43:
                    continue
                results.append(EmailInfo(
                    email_id=item.EntryID,
                    subject=item.Subject or "(No Subject)",
                    sender=item.SenderName or "You",
                    sender_email="",
                    received_date=getattr(item, 'SentOn', item.ReceivedTime),
                    size=item.Size,
                    unread=False,
                    has_attachments=item.Attachments.Count > 0,
                    attachment_count=item.Attachments.Count,
                    folder_path=sent_folder.FolderPath,
                    body_preview=self._body_preview(item, include_body_preview, "Sent Items body preview"),
                ))
            except Exception:
                logger.debug("Skipping unreadable Outlook Sent Items search result", exc_info=True)
        return results

    @staticmethod
    def _body_preview(item, include_body_preview: bool, context: str) -> str:
        if not include_body_preview:
            return ""
        try:
            return (item.Body or "")[:200].replace('\r\n', ' ').replace('\n', ' ')
        except Exception:
            logger.debug(f"Could not read Outlook {context}", exc_info=True)
            return ""

    @staticmethod
    def _search_sender_email(item) -> str:
        try:
            if item.SenderEmailType == "EX":
                sender = item.Sender.GetExchangeUser()
                return sender.PrimarySmtpAddress if sender else ""
            return item.SenderEmailAddress or ""
        except Exception:
            return item.SenderEmailAddress or ""


# ════════════════════════════════════════════════════════════════════
#  Thread-aware singleton factory
# ════════════════════════════════════════════════════════════════════

_main_thread_manager: Optional[OutlookManager] = None
_main_thread_lock = threading.Lock()
_thread_local = threading.local()


def get_outlook_manager() -> OutlookManager:
    """Get a thread-appropriate OutlookManager instance.

    - Main thread: returns a global singleton (shared across all UI callers).
    - Background threads: returns a per-thread cached instance so that
      multiple calls within the same QThread reuse one COM connection
      without paying the connection cost each time.

    COM apartment-threaded objects cannot be shared across threads, so each
    thread must have its own OutlookManager and COM initialisation.
    """
    if threading.current_thread() is threading.main_thread():
        global _main_thread_manager
        if _main_thread_manager is None or not _main_thread_manager.connected:
            with _main_thread_lock:
                if _main_thread_manager is None or not _main_thread_manager.connected:
                    _main_thread_manager = OutlookManager()
        return _main_thread_manager
    else:
        # Per-thread instance cached in threading.local()
        om = getattr(_thread_local, 'outlook_manager', None)
        if om is None or not om.connected:
            om = OutlookManager()
            _thread_local.outlook_manager = om
        return om


def close_thread_outlook_manager():
    """Close and release the OutlookManager for the current background thread.

    Call this in a finally block at the end of QThread.run() to properly
    release COM resources and call CoUninitialize().
    """
    om = getattr(_thread_local, 'outlook_manager', None)
    if om is not None:
        om.close()
        _thread_local.outlook_manager = None
