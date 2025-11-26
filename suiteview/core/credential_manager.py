"""Credential Manager - Encrypt and decrypt database credentials"""

import os
import logging
import tempfile
from pathlib import Path
from cryptography.fernet import Fernet
from typing import Optional

logger = logging.getLogger(__name__)


def _atomic_write(file_path: Path, data: bytes, mode: int = 0o600) -> None:
    """
    Write data to a file atomically using a temporary file and rename.
    This prevents race conditions when multiple processes try to create the file.

    Args:
        file_path: Path to the target file
        data: Bytes to write
        mode: File permission mode (default: owner read/write only)
    """
    # Create temp file in the same directory to ensure same filesystem for atomic rename
    fd, temp_path = tempfile.mkstemp(dir=file_path.parent, prefix='.key_')
    try:
        os.write(fd, data)
        os.close(fd)
        os.chmod(temp_path, mode)
        # Atomic rename (on POSIX systems)
        os.replace(temp_path, file_path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


class CredentialManager:
    """Manages encryption and decryption of database credentials"""

    def __init__(self):
        """Initialize credential manager with encryption key"""
        self._key = self._get_or_create_key()
        self._cipher = Fernet(self._key)

    def _get_or_create_key(self) -> bytes:
        """
        Get or create encryption key for this machine/user.
        Uses a machine-specific key stored in user's home directory.

        This method handles race conditions by using atomic file creation.
        If two processes try to create the key simultaneously, one will win
        and the other will read the winner's key file.
        """
        home = Path.home()
        key_dir = home / '.suiteview'
        key_file = key_dir / '.key'

        # Create directory if it doesn't exist
        key_dir.mkdir(exist_ok=True)

        # Try to read existing key first
        if key_file.exists():
            try:
                with open(key_file, 'rb') as f:
                    key = f.read()
                # Validate key is proper Fernet key (32 bytes base64 encoded = 44 chars)
                if len(key) == 44:
                    logger.debug("Loaded existing encryption key")
                    return key
            except (IOError, OSError) as e:
                logger.warning(f"Could not read existing key file: {e}")

        # Generate new key
        key = Fernet.generate_key()

        try:
            # Use atomic write to prevent race conditions
            _atomic_write(key_file, key, mode=0o600)
            logger.info(f"Generated new encryption key: {key_file}")
        except FileExistsError:
            # Another process created the file first - read their key
            logger.debug("Key file created by another process, reading it")
            with open(key_file, 'rb') as f:
                key = f.read()
        except OSError as e:
            # If atomic write fails but file now exists (race condition), read it
            if key_file.exists():
                logger.debug("Key file appeared during write, reading existing key")
                with open(key_file, 'rb') as f:
                    key = f.read()
            else:
                raise RuntimeError(f"Failed to create encryption key: {e}") from e

        return key

    def encrypt(self, plaintext: str) -> Optional[bytes]:
        """
        Encrypt a plaintext string

        Args:
            plaintext: String to encrypt

        Returns:
            Encrypted bytes, or None if plaintext is empty
        """
        if not plaintext:
            return None

        try:
            encrypted = self._cipher.encrypt(plaintext.encode('utf-8'))
            logger.debug("Encrypted credential")
            return encrypted
        except Exception as e:
            logger.error(f"Failed to encrypt credential: {e}")
            raise

    def decrypt(self, encrypted: bytes) -> Optional[str]:
        """
        Decrypt encrypted bytes to plaintext string

        Args:
            encrypted: Encrypted bytes

        Returns:
            Decrypted string, or None if encrypted is None/empty
        """
        if not encrypted:
            return None

        try:
            decrypted = self._cipher.decrypt(encrypted)
            logger.debug("Decrypted credential")
            return decrypted.decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to decrypt credential: {e}")
            raise

    def encrypt_credentials(self, username: str = None, password: str = None) -> tuple[Optional[bytes], Optional[bytes]]:
        """
        Encrypt username and password

        Args:
            username: Username to encrypt
            password: Password to encrypt

        Returns:
            Tuple of (encrypted_username, encrypted_password)
        """
        encrypted_username = self.encrypt(username) if username else None
        encrypted_password = self.encrypt(password) if password else None
        return encrypted_username, encrypted_password

    def decrypt_credentials(self, encrypted_username: bytes = None,
                          encrypted_password: bytes = None) -> tuple[Optional[str], Optional[str]]:
        """
        Decrypt username and password

        Args:
            encrypted_username: Encrypted username bytes
            encrypted_password: Encrypted password bytes

        Returns:
            Tuple of (username, password)
        """
        username = self.decrypt(encrypted_username) if encrypted_username else None
        password = self.decrypt(encrypted_password) if encrypted_password else None
        return username, password


# Singleton instance
_credential_manager: Optional[CredentialManager] = None


def get_credential_manager() -> CredentialManager:
    """Get or create singleton credential manager instance"""
    global _credential_manager
    if _credential_manager is None:
        _credential_manager = CredentialManager()
    return _credential_manager
