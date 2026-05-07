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
        logger.warning("No ENCRYPTION_KEY set - credentials stored in plaintext!")
        return None

    try:
        if len(key_str) == 44 and key_str.endswith("="):
            key = key_str.encode() if isinstance(key_str, str) else key_str
        else:
            salt = b"lnut_bot_salt_fixed"
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
    if not fernet or not value:
        return value
    try:
        return fernet.encrypt(value.encode()).decode()
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        return value


def decrypt_value(fernet: Fernet | None, value: str) -> str:
    if not fernet or not value:
        return value
    try:
        return fernet.decrypt(value.encode()).decode()
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return value


# === Aliases for core.py compatibility ===

def encrypt_password(password: str) -> str:
    """Encrypt a password using the configured Fernet key."""
    f = get_fernet()
    return encrypt_value(f, password)


def decrypt_password(token: str) -> str:
    """Decrypt a Fernet-encrypted password token."""
    f = get_fernet()
    return decrypt_value(f, token)
