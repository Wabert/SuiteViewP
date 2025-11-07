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
            
            for line in lines:
                item = self._parse_mvs_listing(line)
                if item:
                    items.append(item)
            
            # Return to original path if we changed
            if original_path:
                self.ftp.cwd(original_path)
            
            logger.info(f"Listed {len(items)} items at path: {path or 'current directory'}")
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
        
        Or classic MVS format:
        AC                       01.02   2007/10/01  2008/07/22  10:10    0       ZAB7Y4
        
        Returns:
            Dict with parsed information or None if line can't be parsed
        """
        line = line.strip()
        if not line:
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
                # File/member
                return {
                    'name': parts[-1],
                    'type': 'member',
                    'size': int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0,
                    'modified': ' '.join(parts[-4:-1]) if len(parts) >= 4 else '',
                    'vv_mm': ''
                }
            
            # Try classic MVS format: NAME VV.MM CREATED MODIFIED ...
            elif len(parts) >= 2:
                # Classic MVS listing
                name = parts[0]
                vv_mm = parts[1] if len(parts) > 1 else ''
                created = parts[2] if len(parts) > 2 else ''
                modified = parts[3] if len(parts) > 3 else ''
                size = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 0
                
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
            # First pass: count total lines in dataset
            total_lines = 0
            def count_lines(line):
                nonlocal total_lines
                total_lines += 1
            
            # Count all lines first
            try:
                self.ftp.retrlines(f"RETR '{dataset_name}'", count_lines)
            except Exception as e:
                logger.error(f"Failed to count lines in {dataset_name}: {e}")
                return "", 0
            
            # Second pass: read requested number of lines
            lines = []
            def collect_line(line):
                """Callback to collect lines"""
                lines.append(line)
                # Stop if we've reached max_lines
                if max_lines and len(lines) >= max_lines:
                    raise StopIteration()
            
            # Download dataset using retrlines for ASCII text
            try:
                self.ftp.retrlines(f"RETR '{dataset_name}'", collect_line)
            except StopIteration:
                # Expected when we hit max_lines
                pass
            
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
            
            # Read local file as text
            with open(local_file_path, 'r', encoding='utf-8', errors='ignore') as file:
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
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
