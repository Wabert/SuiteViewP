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
            self.ftp.connect(self.host, self.port, timeout=30)
            
            logger.info(f"Logging in as {self.username}...")
            self.ftp.login(self.username, self.password)
            
            # Set to ASCII mode for mainframe text datasets
            self.ftp.sendcmd('TYPE A')
            
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
            # Navigate to path if specified
            original_path = None
            if path:
                original_path = self.ftp.pwd()
                # Mainframe datasets need quotes around path
                self.ftp.cwd(f"'{path}'")
            
            # Get directory listing
            items = []
            lines = []
            self.ftp.retrlines('LIST', lines.append)
            
            logger.debug(f"Raw FTP listing returned {len(lines)} lines")
            # Log first few raw lines to help debug date parsing
            for i, raw_line in enumerate(lines[:5]):
                logger.info(f"FTP raw line {i}: '{raw_line}'")
            
            for line in lines:
                item = self._parse_mvs_listing(line)
                if item:
                    items.append(item)
                else:
                    logger.debug(f"Skipped unparseable line: {line[:80]}")
            
            # Return to original path if we changed
            if original_path:
                self.ftp.cwd(original_path)
            
            logger.info(f"Listed {len(items)} items at path: {path or 'current directory'} (from {len(lines)} raw lines)")
            return items
            
        except Exception as e:
            logger.error(f"Failed to list datasets at {path}: {e}")
            return []
    
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
        
        # Skip header lines that contain column titles
        line_upper = line.upper()
        if any(header in line_upper for header in ['NAME', 'CHANGED', 'SIZE', 'INIT', 'MOD', 'ID', '-----']):
            if 'VV' in line_upper or 'MM' in line_upper or 'CREATED' in line_upper:
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
        
        try:
            # Read all lines first, then trim if needed
            # This avoids issues with aborting transfers mid-stream
            lines = []
            
            def collect_line(line):
                """Callback to collect lines"""
                lines.append(line)
            
            # Download dataset using retrlines for ASCII text
            try:
                self.ftp.retrlines(f"RETR '{dataset_name}'", collect_line)
            except Exception as e:
                logger.error(f"Failed to read dataset {dataset_name}: {e}")
                # Try to recover the connection
                try:
                    self.ftp.voidcmd('NOOP')
                except:
                    pass
                return "", 0
            
            total_lines = len(lines)
            
            # Trim to max_lines if specified
            if max_lines and len(lines) > max_lines:
                lines = lines[:max_lines]
            
            content = '\n'.join(lines)
            
            logger.info(f"Read {len(lines)} lines from {dataset_name} (total lines: {total_lines})")
            return content, total_lines
            
        except Exception as e:
            logger.error(f"Failed to read dataset {dataset_name}: {e}")
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
            error_msg = f"Permission denied or member not found: {str(e)}"
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
            error_msg = f"Permission denied: {str(e)}"
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
