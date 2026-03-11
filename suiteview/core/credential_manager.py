"""Credential Manager - Encrypt and decrypt database credentials"""

import os
import logging
from pathlib import Path
from cryptography.fernet import Fernet
from typing import Optional

logger = logging.getLogger(__name__)


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
        """
        home = Path.home()
        key_dir = home / '.suiteview'
        key_file = key_dir / '.key'

        # Create directory if it doesn't exist
        key_dir.mkdir(exist_ok=True)

        if key_file.exists():
            # Read existing key
            with open(key_file, 'rb') as f:
                key = f.read()
            logger.debug("Loaded existing encryption key")
        else:
            # Generate new key
            key = Fernet.generate_key()

            # Save key with restricted permissions
            with open(key_file, 'wb') as f:
                f.write(key)

            # Set file permissions to user-only (600)
            os.chmod(key_file, 0o600)

            logger.info(f"Generated new encryption key: {key_file}")

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
