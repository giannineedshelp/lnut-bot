import os
import base64
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("lnut_bot.encryption")

_fernet_instance = None


def get_fernet() -> Fernet | None:
    """Get or create the Fernet cipher instance using the key from .env."""
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    key_str = os.getenv("ENCRYPTION_KEY", "").strip()
    if not key_str:
        logger.warning("No ENCRYPTION_KEY set — credentials will be stored in plaintext!")
        return None

    try:
        # Support both raw base64 keys and passphrase-based keys
        if len(key_str) == 44 and key_str.endswith("="):
            # Looks like a raw Fernet key
            key = key_str.encode()
        else:
            # Derive a key from the passphrase
            salt = b"lnut_bot_salt_fixed"  # Fixed salt for deterministic key
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=480000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(key_str.encode()))

        _fernet_instance = Fernet(key)
        logger.info("Encryption initialized successfully")
        return _fernet_instance
    except Exception as e:
        logger.error(f"Failed to initialize encryption: {e}")
        return None


def encrypt_value(fernet: Fernet | None, value: str) -> str:
    """Encrypt a string value. Returns plaintext if fernet is None."""
    if not fernet or not value:
        return value
    try:
        return fernet.encrypt(value.encode()).decode()
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        return value


def decrypt_value(fernet: Fernet | None, value: str) -> str:
    """Decrypt a string value. Returns as-is if fernet is None."""
    if not fernet or not value:
        return value
    try:
        return fernet.decrypt(value.encode()).decode()
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return value