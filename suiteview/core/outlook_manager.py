"""
Outlook Manager - Integration with Microsoft Outlook via COM

Provides access to Outlook emails, folders, and attachments for the Email Navigator feature.
Uses win32com for COM integration with Outlook application.
"""

import logging
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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
                    
                    # Try to get existing instance first, fall back to creating new one
                    try:
                        self.outlook = win32com.client.GetActiveObject("Outlook.Application")
                        logger.info("Connected to existing Outlook instance")
                    except:
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
        return self.connected
    
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
                        # Handle Exchange addresses
                        if sender_email.startswith('/O='):
                            try:
                                sender_email = item.Sender.GetExchangeUser().PrimarySmtpAddress
                            except:
                                sender_email = item.SenderName
                    except:
                        sender_email = ""
                    
                    # Get body preview
                    body_preview = ""
                    if include_body_preview:
                        try:
                            body = item.Body or ""
                            body_preview = body[:200].replace('\r', ' ').replace('\n', ' ')
                        except:
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
    
    def _is_inline_image(self, attachment) -> bool:
        """Check if attachment is an inline image (not a real attachment)
        
        Args:
            attachment: Outlook attachment object
            
        Returns:
            True if inline image, False if real attachment
        """
        try:
            # Check 1: ContentID property (most reliable)
            try:
                if hasattr(attachment, 'PropertyAccessor'):
                    pr_attach_content_id = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
                    content_id = attachment.PropertyAccessor.GetProperty(pr_attach_content_id)
                    if content_id:
                        logger.debug(f"Skipping inline image with ContentID: {attachment.FileName}")
                        return True
            except:
                pass
            
            # Check 2: Common inline image filename patterns
            filename = attachment.FileName.lower()
            inline_patterns = [
                'image001.', 'image002.', 'image003.', 'image004.', 'image005.',
                'image006.', 'image007.', 'image008.', 'image009.', 'image010.',
                'oledata.mso',
                'header.',
                'footer.',
                'logo.',
                'signature.'
            ]
            
            for pattern in inline_patterns:
                if filename.startswith(pattern):
                    # Additional check: small images are likely inline
                    if attachment.Size < 100000:  # Less than 100KB
                        logger.debug(f"Skipping likely inline image: {attachment.FileName} ({attachment.Size} bytes)")
                        return True
            
            # Check 3: Hidden attachment flag
            try:
                if hasattr(attachment, 'PropertyAccessor'):
                    # PR_ATTACHMENT_HIDDEN
                    pr_attach_hidden = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"
                    is_hidden = attachment.PropertyAccessor.GetProperty(pr_attach_hidden)
                    if is_hidden:
                        logger.debug(f"Skipping hidden attachment: {attachment.FileName}")
                        return True
            except:
                pass
            
            return False
            
        except Exception as e:
            logger.warning(f"Error checking if inline image: {e}")
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
                except:
                    break
            
            return '/'.join(path_parts)
        except:
            return "Unknown"
    
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
                        # Only process MailItem objects with attachments
                        if item.Class != 43 or item.Attachments.Count == 0:
                            continue
                        
                        # Get sender information with failsafe handling
                        display_sender = "(Unknown Sender)"
                        
                        try:
                            sender_email = ""
                            sender_name = ""
                            
                            # Try multiple approaches to get sender info
                            try:
                                # Approach 1: SenderName property
                                raw_sender_name = item.SenderName
                                if raw_sender_name is not None:
                                    sender_name = str(raw_sender_name).strip()
                            except:
                                pass
                            
                            try:
                                # Approach 2: SenderEmailAddress property
                                raw_sender_email = item.SenderEmailAddress
                                if raw_sender_email is not None:
                                    sender_email = str(raw_sender_email).strip()
                                    
                                    # Handle Exchange addresses
                                    if sender_email and sender_email.startswith('/O='):
                                        try:
                                            if item.Sender:
                                                exchange_user = item.Sender.GetExchangeUser()
                                                if exchange_user and exchange_user.PrimarySmtpAddress:
                                                    sender_email = str(exchange_user.PrimarySmtpAddress).strip()
                                        except:
                                            pass
                            except:
                                pass
                            
                            try:
                                # Approach 3: Sender.Name
                                if not sender_name and item.Sender and item.Sender.Name:
                                    sender_name = str(item.Sender.Name).strip()
                            except:
                                pass
                            
                            # Use whatever we found
                            display_sender = sender_name or sender_email or "(Unknown Sender)"
                            
                        except Exception as e:
                            # If all sender extraction fails, log and continue with Unknown
                            logger.warning(f"Sender extraction failed for {item.Subject}: {e}")
                            display_sender = "(Unknown Sender)"
                        
                        # Process each attachment
                        for idx, attachment in enumerate(item.Attachments, 1):
                            try:
                                # Skip embedded items
                                if attachment.Type != 1:  # 1 = olByValue (file attachment)
                                    continue
                                
                                # Skip inline images using comprehensive check
                                if self._is_inline_image(attachment):
                                    continue
                                
                                file_ext = os.path.splitext(attachment.FileName)[1].lower()
                                file_hash = None
                                
                                # Calculate hash if requested
                                if calculate_hash:
                                    try:
                                        # Save temporarily to calculate hash
                                        temp_path = os.path.join(os.getenv('TEMP'), attachment.FileName)
                                        attachment.SaveAsFile(temp_path)
                                        
                                        with open(temp_path, 'rb') as f:
                                            file_hash = hashlib.md5(f.read()).hexdigest()
                                        
                                        os.remove(temp_path)
                                    except Exception as e:
                                        logger.warning(f"Could not calculate hash for {attachment.FileName}: {e}")
                                
                                attach_info = EmailAttachment(
                                    email_id=item.EntryID,
                                    email_subject=item.Subject or "(No Subject)",
                                    email_sender=display_sender,
                                    email_date=item.ReceivedTime,
                                    attachment_name=attachment.FileName,
                                    attachment_type=file_ext or 'unknown',
                                    attachment_size=attachment.Size,
                                    attachment_index=idx,
                                    file_hash=file_hash
                                )
                                
                                all_attachments.append(attach_info)
                            
                            except Exception as e:
                                logger.warning(f"Error processing attachment: {e}")
                                continue
                        
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
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            # Handle file name conflicts
            if os.path.exists(save_path):
                base, ext = os.path.splitext(save_path)
                counter = 1
                while os.path.exists(f"{base}_{counter}{ext}"):
                    counter += 1
                save_path = f"{base}_{counter}{ext}"
            
            attachment.SaveAsFile(save_path)
            logger.info(f"Saved attachment to: {save_path}")
            return True
        
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
            os.makedirs(temp_dir, exist_ok=True)
            
            temp_path = os.path.join(temp_dir, attachment.FileName)
            
            # Only save if not already exists or is old
            if not os.path.exists(temp_path):
                attachment.SaveAsFile(temp_path)
            
            return temp_path
        
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
                            except:
                                sender_email = item.SenderName
                    except:
                        sender_email = ""
                    
                    # Get body preview
                    body_preview = ""
                    if include_body_preview:
                        try:
                            body = item.Body or ""
                            body_preview = body[:200].replace('\r', ' ').replace('\n', ' ')
                        except:
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
                
                # Get sender information with failsafe handling
                display_sender = "(Unknown Sender)"
                
                try:
                    sender_email = ""
                    sender_name = ""
                    
                    # Try to get sender info
                    try:
                        raw_sender_name = item.SenderName
                        if raw_sender_name is not None:
                            sender_name = str(raw_sender_name).strip()
                    except:
                        pass
                    
                    try:
                        raw_sender_email = item.SenderEmailAddress
                        if raw_sender_email is not None:
                            sender_email = str(raw_sender_email).strip()
                            if sender_email and sender_email.startswith('/O='):
                                try:
                                    if item.Sender:
                                        exchange_user = item.Sender.GetExchangeUser()
                                        if exchange_user and exchange_user.PrimarySmtpAddress:
                                            sender_email = str(exchange_user.PrimarySmtpAddress).strip()
                                except:
                                    pass
                    except:
                        pass
                    
                    try:
                        if not sender_name and item.Sender and item.Sender.Name:
                            sender_name = str(item.Sender.Name).strip()
                    except:
                        pass
                    
                    # Fallback to email info
                    if not sender_name and hasattr(email, 'sender') and email.sender:
                        sender_name = str(email.sender).strip()
                    if not sender_email and hasattr(email, 'sender_email') and email.sender_email:
                        sender_email = str(email.sender_email).strip()
                    
                    display_sender = sender_name or sender_email or "(Unknown Sender)"
                    
                except Exception as e:
                    logger.warning(f"Sender extraction failed for {item.Subject}: {e}")
                    display_sender = "(Unknown Sender)"
                
                # Process each attachment
                for idx, attachment in enumerate(item.Attachments, 1):
                    try:
                        # Skip embedded items
                        if attachment.Type != 1:  # 1 = olByValue (file attachment)
                            continue
                        
                        # Skip inline images using comprehensive check
                        if self._is_inline_image(attachment):
                            continue
                        
                        file_ext = os.path.splitext(attachment.FileName)[1].lower()
                        file_hash = None
                        
                        # Calculate hash if requested
                        if calculate_hash:
                            try:
                                temp_path = os.path.join(os.getenv('TEMP'), attachment.FileName)
                                attachment.SaveAsFile(temp_path)
                                
                                with open(temp_path, 'rb') as f:
                                    file_hash = hashlib.md5(f.read()).hexdigest()
                                
                                os.remove(temp_path)
                            except Exception as e:
                                logger.warning(f"Could not calculate hash for {attachment.FileName}: {e}")
                        
                        attach_info = EmailAttachment(
                            email_id=item.EntryID,
                            email_subject=item.Subject or "(No Subject)",
                            email_sender=display_sender,
                            email_date=item.ReceivedTime,
                            attachment_name=attachment.FileName,
                            attachment_type=file_ext or 'unknown',
                            attachment_size=attachment.Size,
                            attachment_index=idx,
                            file_hash=file_hash
                        )
                        
                        attachments.append(attach_info)
                    
                    except Exception as e:
                        logger.warning(f"Error processing attachment {idx}: {e}")
                        continue
            
            except Exception as e:
                logger.warning(f"Error accessing email attachments: {e}")
                continue
        
        logger.info(f"Found {len(attachments)} attachments from {len(emails)} emails")
        return attachments


# Singleton instance
_outlook_manager = None


def get_outlook_manager() -> OutlookManager:
    """Get singleton instance of OutlookManager"""
    global _outlook_manager
    if _outlook_manager is None:
        _outlook_manager = OutlookManager()
    return _outlook_manager
