"""FTP Manager for connecting to mainframe datasets via FTP"""

import ftplib
import io
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class MainframeFTPManager:
    """Manages FTP connections to mainframe systems for dataset access"""
    
    def __init__(self, host: str, username: str, password: str, port: int = 21, initial_path: str = ''):
        """
        Initialize mainframe FTP manager
        
        Args:
            host: FTP server hostname
            username: FTP username
            password: FTP password  
            port: FTP port (default 21)
            initial_path: Initial path/dataset qualifier (e.g., 'd03.aa0139.CKAS.cdf.data')
        """
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.initial_path = initial_path.strip("'\"")  # Remove quotes if present
        self.ftp: Optional[ftplib.FTP] = None
        self.connected = False
        self.keepalive_timer = None
        # Note: May need to pause keepalive during active transfers if we see interference
        self.on_reconnect_callback = None  # Optional callback for status updates
    
    def connect(self) -> bool:
        """
        Connect to mainframe FTP server
        
        Returns:
            bool: True if connection successful, False otherwise
            
        Raises:
            Exception: If connection fails with detailed error message
        """
        try:
            self.ftp = ftplib.FTP()
            logger.info(f"Attempting to connect to {self.host}:{self.port}...")
            # 5-minute timeout to prevent premature disconnects
            self.ftp.connect(self.host, self.port, timeout=300)
            
            logger.info(f"Logging in as {self.username}...")
            self.ftp.login(self.username, self.password)
            
            # Set to ASCII mode for mainframe text datasets
            self.ftp.sendcmd('TYPE A')
            
            # Start keepalive timer to prevent idle timeout
            self._start_keepalive()
            
            # Navigate to initial path if specified
            if self.initial_path:
                try:
                    self.ftp.cwd(f"'{self.initial_path}'")
                    logger.info(f"Changed to initial path: {self.initial_path}")
                except Exception as e:
                    logger.warning(f"Could not change to initial path {self.initial_path}: {e}")
            
            self.connected = True
            logger.info(f"Successfully connected to mainframe FTP: {self.host}:{self.port}")
            return True
            
        except ftplib.error_perm as e:
            error_str = str(e)
            # Check if this is a password-related error
            if "530" in error_str or "PASS" in error_str or "password" in error_str.lower():
                error_msg = (
                    f"Authentication failed: {error_str}\n\n"
                    f"This may indicate your mainframe password has expired or changed.\n"
                    f"To update your password:\n"
                    f"1. Go to the Connections tab\n"
                    f"2. Right-click on 'MAINFRAME_FTP'\n"
                    f"3. Select 'Update Password for All Children'"
                )
            else:
                error_msg = f"Authentication failed: {error_str}"
            logger.error(error_msg)
            self.connected = False
            raise Exception(error_msg)
            
        except (ConnectionRefusedError, OSError) as e:
            if "timed out" in str(e).lower():
                error_msg = f"Connection timeout - mainframe may be down or unreachable"
            elif "refused" in str(e).lower():
                error_msg = f"Connection refused - FTP service may be down"
            else:
                error_msg = f"Network error: {str(e)}"
            logger.error(error_msg)
            self.connected = False
            raise Exception(error_msg)
            
        except Exception as e:
            error_msg = f"Connection failed: {str(e)}"
            logger.error(error_msg)
            self.connected = False
            raise Exception(error_msg)
    
    def disconnect(self):
        """Disconnect from FTP server"""
        # Stop keepalive timer
        if self.keepalive_timer:
            try:
                self.keepalive_timer.stop()
                self.keepalive_timer = None
            except:
                pass
        
        if self.ftp:
            try:
                self.ftp.quit()
            except:
                try:
                    self.ftp.close()
                except:
                    pass
            self.ftp = None
        self.connected = False
        logger.info("Disconnected from mainframe FTP")
    
    def _start_keepalive(self):
        """Start keepalive timer to prevent connection timeout"""
        try:
            from PyQt6.QtCore import QTimer
            if self.keepalive_timer:
                self.keepalive_timer.stop()
            
            self.keepalive_timer = QTimer()
            self.keepalive_timer.timeout.connect(self._send_keepalive)
            self.keepalive_timer.start(300000)  # 5 minutes
            logger.debug("Keepalive timer started (5 min interval)")
        except Exception as e:
            logger.warning(f"Could not start keepalive timer: {e}")
    
    def _send_keepalive(self):
        """Send NOOP to keep connection alive"""
        try:
            if self.ftp and self.connected:
                self.ftp.voidcmd('NOOP')
                logger.debug("Sent keepalive NOOP")
        except Exception as e:
            logger.warning(f"Keepalive failed: {e}")
            self.connected = False
    
    def _ensure_connected(self) -> bool:
        """
        Ensure connection is alive, reconnect if needed.
        
        Returns:
            True if connected, False if reconnection failed
        """
        if not self.connected or not self.ftp:
            logger.warning("Not connected, attempting to reconnect...")
            return self._attempt_reconnect()
        
        try:
            self.ftp.voidcmd('NOOP')
            return True
        except:
            logger.warning("Connection lost, attempting to reconnect...")
            return self._attempt_reconnect()
    
    def _attempt_reconnect(self) -> bool:
        """Attempt to reconnect to FTP server"""
        try:
            self.disconnect()
            success = self.connect()
            
            if success and self.on_reconnect_callback:
                # Notify UI of reconnection (non-blocking footer status)
                try:
                    self.on_reconnect_callback("Reconnected to mainframe")
                except Exception as e:
                    logger.debug(f"Reconnect callback failed: {e}")
            
            return success
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            return False
    
    def is_alive(self) -> bool:
        """
        Check if FTP connection is still alive
        
        Returns:
            bool: True if connection is alive, False otherwise
        """
        if not self.connected or not self.ftp:
            return False
        
        try:
            # Send NOOP command to check if connection is alive
            self.ftp.voidcmd("NOOP")
            return True
        except (ftplib.error_temp, ftplib.error_perm, OSError, EOFError) as e:
            logger.warning(f"Connection check failed: {e}")
            self.connected = False
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking connection: {e}")
            self.connected = False
            return False
    
    def list_datasets(self, path: str = '') -> List[Dict[str, any]]:
        """
        List datasets/members at specified path
        
        Args:
            path: Dataset path (e.g., 'D03.AA0139.CKAS.CIRF.DATA')
                  If empty, lists current directory
        
        Returns:
            List of dictionaries with dataset info:
                - name: Dataset/member name
                - type: 'dataset' or 'member' or 'directory'
                - size: Size in bytes (if available)
                - modified: Last modified date (if available)
                - vv_mm: Version.Modification (mainframe specific)
        """
        if not self.connected:
            logger.error("Not connected to FTP server")
            return []
        
        try:
            # Ensure connection is alive (auto-reconnect if needed)
            if not self._ensure_connected():
                logger.error("Cannot list datasets - connection unavailable")
                return []
            
            # Navigate to path if specified
            original_path = None
            if path:
                try:
                    original_path = self.ftp.pwd()
                    # Mainframe datasets need quotes around path
                    self.ftp.cwd(f"'{path}'")
                    logger.debug(f"Changed to path: {path}")
                except Exception as e:
                    logger.error(f"Failed to change to path {path}: {e}")
                    return []
            
            # Get directory listing
            items = []
            lines = []
            try:
                self.ftp.retrlines('LIST', lines.append)
                logger.debug(f"Raw FTP listing returned {len(lines)} lines")
            except ftplib.error_perm as e:
                error_msg = str(e)
                # FTP success codes (200, 226, 250) are sometimes returned as exceptions
                if any(code in error_msg for code in ['200', '226', '250']):
                    logger.debug(f"FTP success message: {error_msg}")
                    # Data was transferred successfully, continue
                else:
                    logger.error(f"Permission error during LIST: {error_msg}")
                    if original_path:
                        try:
                            self.ftp.cwd(original_path)
                        except:
                            pass
                    return []
            except (EOFError, OSError, ConnectionError) as e:
                logger.error(f"Connection lost during LIST: {e}")
                self.connected = False
                if original_path:
                    try:
                        self.ftp.cwd(original_path)
                    except:
                        pass
                return []
            except Exception as e:
                logger.error(f"Error during LIST command: {e}")
                if original_path:
                    try:
                        self.ftp.cwd(original_path)
                    except:
                        pass
                return []
            
            # Parse all lines - they could be dataset attributes OR members
            for line in lines:
                # Try to parse as dataset attribute line first
                dataset_attr = self._parse_dataset_attributes(line)
                if dataset_attr:
                    # This is a dataset attribute line
                    items.append(dataset_attr)
                else:
                    # Try to parse as member
                    item = self._parse_mvs_listing(line)
                    if item:
                        items.append(item)
            
            # Return to original path if we changed
            if original_path:
                try:
                    self.ftp.cwd(original_path)
                    logger.debug(f"Returned to original path: {original_path}")
                except Exception as e:
                    logger.warning(f"Failed to return to original path: {e}")
            
            logger.info(f"Listed {len(items)} items at path: {path or 'current directory'} (from {len(lines)} raw lines)")
            return items
            
        except Exception as e:
            logger.error(f"Failed to list datasets at {path}: {e}")
            return []
    
    def _parse_dataset_attributes(self, line: str) -> Optional[Dict[str, any]]:
        """
        Parse dataset attribute line from MVS FTP listing
        
        Format: Volume Unit Referred Ext Used Recfm Lrecl BlkSz Dsorg Dsname
        Example: A8C201 3390 2025/12/29 1 15 FBA 133 13300 PS UTABLES
        
        Returns:
            Dict with dataset attributes or None if not a dataset attribute line
        """
        line = line.strip()
        if not line:
            return None
        
        # Skip header lines
        if any(keyword in line.upper() for keyword in ['VOLUME', 'UNIT', 'REFERRED', 'DSORG', 'DSNAME', '-----']):
            return None
        
        parts = line.split()
        if len(parts) < 2:
            return None
        
        # The dataset name is ALWAYS the last field on the line
        dsname = parts[-1]
        
        # Check if this looks like a dataset attribute line
        # Must have device type (3390, 3380, etc.) or Dsorg (PO, PS, GDG, etc.) or "Migrated"
        has_device = any(dev in parts for dev in ['3390', '3380', '3350', 'Tape'])
        has_dsorg = any(org in parts for org in ['PO', 'PS', 'DA', 'IS', 'VS', 'GDG'])
        has_migrated = 'Migrated' in parts
        
        if not (has_device or has_dsorg or has_migrated):
            return None
        
        try:
            # Initialize all fields with defaults
            volume = ''
            unit = ''
            referred = ''
            ext = ''
            used = ''
            recfm = ''
            lrecl = ''
            blksz = ''
            dsorg = ''
            
            # If we have 10+ parts, it's a full dataset attribute line
            if len(parts) >= 10:
                volume = parts[0]
                unit = parts[1]
                referred = parts[2] if '/' in parts[2] else ''
                ext = parts[3] if parts[3].isdigit() else ''
                used = parts[4] if parts[4].isdigit() else ''
                recfm = parts[5]
                lrecl = parts[6] if parts[6].isdigit() else ''
                blksz = parts[7] if parts[7].isdigit() else ''
                dsorg = parts[8]
            # If we have 2 parts, it's likely "GDG DSNAME" or "Migrated DSNAME"
            elif len(parts) == 2:
                if parts[0] == 'GDG':
                    dsorg = 'GDG'
                elif parts[0] == 'Migrated':
                    volume = 'Migrated'
                    # Try to determine dsorg from dataset name pattern
                    if '.G' in dsname and 'V00' in dsname:
                        dsorg = 'GDG'  # GDG generation
            # If we have more than 2 but less than 10, try to extract what we can
            elif len(parts) > 2:
                # Check for common patterns
                if 'GDG' in parts:
                    dsorg = 'GDG'
                if 'Migrated' in parts:
                    volume = 'Migrated'
                # Look for device types
                for dev in ['3390', '3380', '3350', 'Tape']:
                    if dev in parts:
                        unit = dev
                        break
                # Look for date pattern
                for part in parts:
                    if '/' in part and len(part) == 10:
                        referred = part
                        break
            
            return {
                'name': dsname,
                'type': 'dataset',
                'volume': volume,
                'unit': unit,
                'referred': referred,
                'ext': ext,
                'used': used,
                'recfm': recfm,
                'lrecl': lrecl,
                'blksz': blksz,
                'dsorg': dsorg,
                'is_dataset': True
            }
        except Exception as e:
            logger.debug(f"Failed to parse dataset attributes from: {line} - {e}")
            return None
    
    def _parse_mvs_listing(self, line: str) -> Optional[Dict[str, any]]:
        """
        Parse MVS/z/OS FTP listing line
        
        MVS listing format examples:
        -rw-r--r--   1 user     group       10 10 Jan 01 2007 AC
        drwxr-xr-x   2 user     group        0     Oct 01 2008 SUBDIR
        
        Or classic MVS/ISPF format with stats:
        EXECULC3  01.00 2025/12/02 2025/12/02 10:12 28990 28990     0 AD9G44
        (NAME  VV.MM CREATED CHANGED TIME SIZE INIT MOD ID)
        
        Or simple member list without stats:
        CLTG1                                         604 40604     0 AD9G44
        
        Returns:
            Dict with parsed information or None if line can't be parsed
        """
        line = line.strip()
        if not line:
            return None
        
        # Skip header lines that contain column titles or dataset information
        line_upper = line.upper()
        
        # First check: Skip obvious header/separator lines
        if any(keyword in line_upper for keyword in ['-----', 'NAME', 'VV.MM', 'CREATED', 'CHANGED']):
            return None
        
        # Second check: Skip dataset-level information lines (Volume info, Unit info, etc.)
        # These appear before member listings in MVS FTP responses
        if any(keyword in line_upper for keyword in ['VOLUME', 'UNIT', 'REFERRED', 'RECFM', 'LRECL', 'BLKSZ', 'DSORG', 'DSNAME']):
            logger.debug(f"Skipping dataset info line: {line}")
            return None
        
        # Third check: Skip dataset attribute lines (these have device types and org)
        # Example: "A8C201 3390   2025/12/29  1  45  FB      80  6160  PO  D03.AA0139.RESTART.SMOPRT"
        if any(device in line_upper for device in ['3390', '3380', '3350']):  # DASD device types
            logger.debug(f"Skipping dataset attribute line (device type): {line}")
            return None
        
        # Check for dataset organization types (PO, PS, DA, etc.) in typical attribute positions
        parts_check = line.split()
        if len(parts_check) > 2:
            # Look for record formats (FB, VB, U, etc.) and dataset orgs (PO, PS, DA)
            for part in parts_check:
                if part.upper() in ['FB', 'VB', 'VBS', 'FBA', 'U', 'PO', 'PS', 'DA', 'IS', 'VS']:
                    logger.debug(f"Skipping dataset attribute line (found {part}): {line}")
                    return None
        
        try:
            parts = line.split()
            if not parts:
                return None
            
            # Try Unix-style listing first (more common with modern FTP)
            if line.startswith('d'):
                # Directory
                return {
                    'name': parts[-1],
                    'type': 'directory',
                    'size': 0,
                    'modified': ' '.join(parts[-4:-1]) if len(parts) >= 4 else '',
                    'vv_mm': ''
                }
            elif line.startswith('-'):
                # File/member - Unix style
                return {
                    'name': parts[-1],
                    'type': 'member',
                    'size': int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0,
                    'modified': ' '.join(parts[-4:-1]) if len(parts) >= 4 else '',
                    'vv_mm': ''
                }
            
            # Classic MVS/ISPF format
            name = parts[0]
            
            # Validate that name looks like a valid member name
            if not name or name.startswith('*') or name.startswith('-'):
                return None
            
            # MVS member names must be 1-8 characters and follow naming rules:
            # - Start with letter or national char (@, #, $)
            # - Contain only alphanumeric or national chars
            # - Max 8 characters
            if len(name) > 8:
                logger.debug(f"Skipping '{name}' - too long for member name (>{len(name)} chars)")
                return None
            
            # Check if first character is valid (letter or @#$)
            if not (name[0].isalpha() or name[0] in '@#$'):
                logger.debug(f"Skipping '{name}' - invalid first character")
                return None
            
            # Check if all characters are valid
            if not all(c.isalnum() or c in '@#$' for c in name):
                logger.debug(f"Skipping '{name}' - contains invalid characters")
                return None
            
            # Try to extract other fields if they exist
            vv_mm = ''
            modified = ''
            created = ''
            size = 0
            
            if len(parts) >= 2:
                # Check if second field looks like VV.MM format (e.g., 01.00, 01.02)
                # This indicates full ISPF statistics are present
                if '.' in parts[1] and len(parts[1]) <= 6 and parts[1].replace('.', '').isdigit():
                    vv_mm = parts[1]
                    # Full format: NAME VV.MM CREATED CHANGED TIME SIZE INIT MOD ID
                    if len(parts) >= 3 and '/' in parts[2]:
                        created = parts[2]
                    if len(parts) >= 4 and '/' in parts[3]:
                        modified = parts[3]
                        # Include time if present
                        if len(parts) >= 5 and ':' in parts[4]:
                            modified = f"{parts[3]} {parts[4]}"
                            # Size is at index 5
                            if len(parts) >= 6 and parts[5].isdigit():
                                size = int(parts[5])
                        elif len(parts) >= 5 and parts[4].isdigit():
                            # No time, size at index 4
                            size = int(parts[4])
                    logger.debug(f"Parsed ISPF member '{name}' VV.MM={vv_mm} modified='{modified}'")
                else:
                    # Simple format without ISPF stats - just name and some numbers
                    # Try to find size (usually a larger number)
                    for p in parts[1:]:
                        if p.isdigit():
                            size = int(p)
                            break
                    logger.debug(f"Parsed simple member '{name}' (no ISPF stats)")
            
            return {
                'name': name,
                'type': 'member',
                'size': size,
                'modified': modified,
                'created': created,
                'vv_mm': vv_mm
            }
            
        except Exception as e:
            logger.debug(f"Could not parse MVS listing line: {line} - {e}")
            # Even if parsing fails, try to return at least the name if we can extract it
            try:
                parts = line.split()
                if parts and parts[0] and not parts[0].startswith(('-', '*')):
                    return {
                        'name': parts[0],
                        'type': 'member',
                        'size': 0,
                        'modified': '',
                        'created': '',
                        'vv_mm': ''
                    }
            except:
                pass
        
        return None
    
    def read_dataset(self, dataset_name: str, max_lines: int = 1000) -> Tuple[str, int]:
        """
        Read contents of a dataset/member
        
        Args:
            dataset_name: Name of dataset/member to read
            max_lines: Maximum number of lines to read (default 1000)
        
        Returns:
            Tuple of (content as string, total lines in dataset)
        """
        if not self.connected:
            logger.error("Not connected to FTP server")
            return "", 0
        
        # Save current directory to restore later
        original_dir = None
        try:
            original_dir = self.ftp.pwd()
            logger.debug(f"Saved current directory: {original_dir}")
        except Exception as e:
            logger.warning(f"Could not get current directory: {e}")
        
        try:
            # Ensure connection is alive (auto-reconnect if needed)
            if not self._ensure_connected():
                logger.error("Cannot read dataset - connection unavailable")
                return "", 0
            
            # Read all lines - use retrlines which handles EBCDIC→ASCII conversion properly
            lines = []
            
            def collect_line(line):
                """Callback to collect lines"""
                lines.append(line)
            
            # Download dataset using retrlines
            try:
                # Log current directory for debugging
                try:
                    current_dir = self.ftp.pwd()
                    logger.debug(f"Current FTP directory: {current_dir}")
                except:
                    pass
                
                logger.info(f"Attempting to read dataset: {dataset_name}")
                
                # Capture the response from the RETR command
                ftp_response = []
                original_callback = self.ftp.lastresp if hasattr(self.ftp, 'lastresp') else None
                
                self.ftp.retrlines(f"RETR '{dataset_name}'", collect_line)
                
                # Log the FTP server's response
                if hasattr(self.ftp, 'lastresp'):
                    logger.info(f"FTP server response: {self.ftp.lastresp}")
                
                logger.info(f"RETR completed: {len(lines)} lines")
            except ftplib.error_perm as e:
                error_msg = str(e)
                # FTP success codes are sometimes returned as exceptions
                if any(code in error_msg for code in ['200', '226', '250']):
                    logger.debug(f"FTP success message: {error_msg}")
                    # Data was transferred successfully
                else:
                    logger.error(f"Permission error reading {dataset_name}: {error_msg}")
                    if '550' in error_msg or 'Not found' in error_msg:
                        logger.warning(f"Dataset not found: {dataset_name}")
                    
                    # Critical: FTP state may be corrupted after failed RETR
                    # Force reconnect to clear any pending state
                    logger.warning("Forcing reconnect to clear FTP state after error")
                    self._attempt_reconnect()
                    
                    return "", 0
            except UnicodeDecodeError as e:
                # This happens when retrlines() tries to decode bytes that aren't valid UTF-8
                # The FTP connection is now in a bad state
                logger.error(f"UTF-8 decode error reading {dataset_name}: {e}")
                logger.warning("Dataset contains binary/non-text data - forcing reconnect")
                
                # Force reconnect to clear corrupted FTP state
                self._attempt_reconnect()
                
                return "", 0
            except (ftplib.error_temp, EOFError, OSError, ConnectionError) as e:
                logger.error(f"Connection error reading {dataset_name}: {e}")
                self.connected = False
                return "", 0
            except Exception as e:
                logger.error(f"Failed to read dataset {dataset_name}: {e}")
                return "", 0
            
            total_lines = len(lines)
            
            # Log results
            if total_lines == 0:
                logger.warning(f"Dataset {dataset_name} returned 0 lines (may be empty)")
            else:
                logger.info(f"Successfully read {total_lines} lines from {dataset_name}")
            
            # Trim to max_lines if specified
            if max_lines and len(lines) > max_lines:
                lines = lines[:max_lines]
            
            content = '\n'.join(lines)
            
            # Restore original directory
            if original_dir:
                try:
                    self.ftp.cwd(original_dir)
                    logger.debug(f"Restored directory to: {original_dir}")
                except Exception as e:
                    logger.warning(f"Could not restore directory: {e}")
            
            return content, total_lines
            
        except Exception as e:
            logger.error(f"Unexpected error reading dataset {dataset_name}: {e}")
            
            # Try to restore directory even on error
            if original_dir:
                try:
                    self.ftp.cwd(original_dir)
                    logger.debug(f"Restored directory after error to: {original_dir}")
                except:
                    pass
            
            return "", 0
    def get_dataset_info(self, dataset_name: str) -> Optional[Dict[str, any]]:
        """
        Get information about a specific dataset
        
        Args:
            dataset_name: Name of dataset
        
        Returns:
            Dict with dataset information or None if not found
        """
        if not self.connected:
            return None
        
        try:
            # Get size using SIZE command
            size_response = self.ftp.sendcmd(f'SIZE {dataset_name}')
            size = int(size_response.split()[1]) if size_response else 0
            
            # Get modification time using MDTM command
            try:
                mdtm_response = self.ftp.sendcmd(f'MDTM {dataset_name}')
                modified = mdtm_response.split()[1] if mdtm_response else ''
            except:
                modified = ''
            
            return {
                'name': dataset_name,
                'size': size,
                'modified': modified,
                'type': 'dataset'
            }
            
        except Exception as e:
            logger.error(f"Failed to get info for dataset {dataset_name}: {e}")
            return None
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test FTP connection
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            if not self.connected:
                success = self.connect()
                if not success:
                    return False, "Failed to connect to FTP server"
            
            # Try to get current directory as a test
            pwd = self.ftp.pwd()
            
            return True, f"Successfully connected to {self.host}. Current path: {pwd}"
            
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"
    
    def upload_file(self, local_file_path: str, remote_dataset_name: str) -> Tuple[bool, str]:
        """
        Upload a local file to mainframe dataset
        
        Args:
            local_file_path: Path to local file to upload
            remote_dataset_name: Target dataset name on mainframe (e.g., 'D03.AA0139.TEST.DATA')
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.connected:
            logger.error("Not connected to FTP server")
            return False, "Not connected to FTP server"
        
        try:
            # Ensure dataset name is properly formatted
            if not remote_dataset_name.startswith("'") and not remote_dataset_name.startswith('"'):
                remote_dataset_name = f"'{remote_dataset_name}'"
            
            # Read local file
            with open(local_file_path, 'rb') as file:
                # Use STOR command to upload
                self.ftp.storbinary(f'STOR {remote_dataset_name}', file)
            
            logger.info(f"Successfully uploaded {local_file_path} to {remote_dataset_name}")
            return True, f"Successfully uploaded to {remote_dataset_name}"
            
        except FileNotFoundError:
            error_msg = f"Local file not found: {local_file_path}"
            logger.error(error_msg)
            return False, error_msg
            
        except ftplib.error_perm as e:
            error_msg = f"Permission denied or dataset error: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
            
        except Exception as e:
            error_msg = f"Upload failed: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def upload_file_as_text(self, local_file_path: str, remote_dataset_name: str) -> Tuple[bool, str]:
        """
        Upload a local file to mainframe dataset as text (ASCII mode)
        Use this for text files, CSV, etc.
        
        Args:
            local_file_path: Path to local file to upload
            remote_dataset_name: Target dataset name on mainframe
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.connected:
            logger.error("Not connected to FTP server")
            return False, "Not connected to FTP server"
        
        try:
            # Ensure dataset name is properly formatted
            if not remote_dataset_name.startswith("'") and not remote_dataset_name.startswith('"'):
                remote_dataset_name = f"'{remote_dataset_name}'"
            
            # Set ASCII mode
            self.ftp.sendcmd('TYPE A')
            
            # Read local file as binary (storlines requires binary mode)
            with open(local_file_path, 'rb') as file:
                # Store lines
                self.ftp.storlines(f'STOR {remote_dataset_name}', file)
            
            logger.info(f"Successfully uploaded {local_file_path} to {remote_dataset_name} (text mode)")
            return True, f"Successfully uploaded to {remote_dataset_name}"
            
        except FileNotFoundError:
            error_msg = f"Local file not found: {local_file_path}"
            logger.error(error_msg)
            return False, error_msg
            
        except ftplib.error_perm as e:
            error_msg = f"Permission denied or dataset error: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
            
        except Exception as e:
            error_msg = f"Upload failed: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def delete_member(self, member_path: str) -> Tuple[bool, str]:
        """
        Delete a member from a PDS
        
        Args:
            member_path: Full member path like 'D03.AA0139.CKAS.PLANIAF(MEMBER)'
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.connected:
            logger.error("Not connected to FTP server")
            return False, "Not connected to FTP server"
        
        try:
            # Use DELE command to delete
            self.ftp.delete(f"'{member_path}'")
            
            logger.info(f"Successfully deleted {member_path}")
            return True, f"Successfully deleted {member_path}"
            
        except ftplib.error_perm as e:
            error_str = str(e)
            if "User not authorized" in error_str or "not authorized" in error_str.lower():
                error_msg = f"Access denied: You do not have permission to delete members in this dataset.\n\nMainframe Response: {error_str}"
            elif "not found" in error_str.lower():
                error_msg = f"Member not found: {member_path}\n\nMainframe Response: {error_str}"
            else:
                error_msg = f"Permission denied or member not found.\n\nMainframe Response: {error_str}"
            logger.error(error_msg)
            return False, error_msg
            
        except Exception as e:
            error_msg = f"Delete failed: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def write_content(self, member_path: str, content: str) -> Tuple[bool, str]:
        """
        Write content to a member (for editing)
        
        Args:
            member_path: Full member path like 'D03.AA0139.CKAS.PLANIAF(MEMBER)'
            content: Text content to write
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.connected:
            logger.error("Not connected to FTP server")
            return False, "Not connected to FTP server"
        
        try:
            # Set ASCII mode for text
            self.ftp.sendcmd('TYPE A')
            
            # Convert content to bytes for storlines
            from io import BytesIO
            content_bytes = BytesIO(content.encode('utf-8'))
            
            # Store the content
            self.ftp.storlines(f"STOR '{member_path}'", content_bytes)
            
            logger.info(f"Successfully wrote content to {member_path}")
            return True, f"Successfully saved {member_path}"
            
        except ftplib.error_perm as e:
            error_str = str(e)
            if "User not authorized" in error_str or "not authorized" in error_str.lower():
                error_msg = f"Access denied: You do not have permission to modify members in this dataset.\n\nYour mainframe account may have read-only access.\n\nMainframe Response: {error_str}"
            elif "not found" in error_str.lower():
                error_msg = f"Member not found: {member_path}\n\nMainframe Response: {error_str}"
            else:
                error_msg = f"Permission denied.\n\nMainframe Response: {error_str}"
            logger.error(error_msg)
            return False, error_msg
            
        except Exception as e:
            error_msg = f"Write failed: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
