import json
from pathlib import Path
import os

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
ACCOUNTS_FILE = DATA_DIR / "accounts.json"
SETTINGS_FILE = DATA_DIR / "settings.json"

DATA_DIR.mkdir(exist_ok=True)


# DO NOT load dotenv here anymore
# DO NOT import encryption here

# =========================
# ACCOUNTS
# =========================

def _load(file):
    if not file.exists():
        return {}
    try:
        return json.loads(file.read_text())
    except Exception:
        return {}

def _save(file, data):
    file.write_text(json.dumps(data, indent=2))


def set_account(user_id, username, password_encrypted):
    data = _load(ACCOUNTS_FILE)
    data[user_id] = {
        "username": username,
        "password_encrypted": password_encrypted
    }
    _save(ACCOUNTS_FILE, data)


def get_account(user_id):
    return _load(ACCOUNTS_FILE).get(user_id)


def remove_account(user_id):
    data = _load(ACCOUNTS_FILE)
    if user_id in data:
        del data[user_id]
        _save(ACCOUNTS_FILE, data)
        return True
    return False


# =========================
# PASSWORD (IMPORTANT FIX)
# =========================

def get_decrypted_password(user_id):
    from utils.encryption import decrypt_password  # moved INSIDE function

    acc = get_account(user_id)
    if not acc:
        return None

    try:
        return decrypt_password(acc["password_encrypted"])
    except:
        return None


# =========================
# SETTINGS
# =========================

def get_user_settings(user_id):
    data = _load(SETTINGS_FILE).get(user_id, {})
    return {
        "speed": data.get("speed", 10000),
        "accuracy_min": data.get("accuracy_min", 100),
        "accuracy_max": data.get("accuracy_max", 100),
    }


def save_user_settings(user_id, settings):
    data = _load(SETTINGS_FILE)
    data[user_id] = settings
    _save(SETTINGS_FILE, data)