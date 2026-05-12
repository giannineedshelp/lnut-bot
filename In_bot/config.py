"""
Configuration and settings manager for LanguageNut bot.

Handles per-guild account credentials + automation settings with safe I/O.
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("lnut_bot.config")

# Allow config path to be overridden via env (used by Docker / Fly.io for persistent volume)
_config_dir = os.getenv("CONFIG_DIR", "")
if _config_dir:
    CONFIG_PATH = Path(_config_dir) / "config.json"
else:
    CONFIG_PATH = Path("config.json")

_LOCK = threading.Lock()

DEFAULT_SETTINGS: dict[str, Any] = {
    "speed": 10.0,
    "min_accuracy": 85,
    "max_accuracy": 92,
    "stealth_enabled": True,
    "concurrency": 3,
    "auto_retry": True,
    "retry_attempts": 2,
    # Per-question timing: each vocab gets a random time in [min, max] seconds
    # Total timestamp = cumulative sum of per-question random values
    "min_seconds_per_question": 5.0,
    "max_seconds_per_question": 8.0,
    # XP earned per task item (multiplied by vocab count for total score)
    "xp_per_task": 200,
}


def _default_config() -> dict:
    return {"accounts": {}, "guild_settings": {}}


def load_config() -> dict:
    """Load the config file, creating it if it doesn't exist."""
    with _LOCK:
        if not CONFIG_PATH.exists():
            default = _default_config()
            _save(default)
            return default
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if "accounts" not in data:
                data["accounts"] = {}
            if "guild_settings" not in data:
                data["guild_settings"] = {}
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Config corrupt, resetting: {e}")
            default = _default_config()
            _save(default)
            return default


def _save(config: dict) -> None:
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    tmp.replace(CONFIG_PATH)


def save_config(config: dict) -> None:
    """Save config to disk atomically."""
    with _LOCK:
        _save(config)


# ==========================================================
# ACCOUNTS
# ==========================================================
def get_account(guild_id: int) -> dict | None:
    """Get account config for a guild, or None."""
    config = load_config()
    return config.get("accounts", {}).get(str(guild_id))


def set_account(guild_id: int, username: str, password: str, token: str = "") -> dict:
    """Set account credentials for a guild."""
    config = load_config()
    config.setdefault("accounts", {})[str(guild_id)] = {
        "username": username,
        "password": password,
        "token": token,
    }
    save_config(config)
    return config["accounts"][str(guild_id)]


def update_token(guild_id: int, token: str) -> None:
    """Update only the token for an existing account."""
    config = load_config()
    acct = config.get("accounts", {}).get(str(guild_id))
    if acct:
        acct["token"] = token
        save_config(config)


def remove_account(guild_id: int) -> bool:
    """Remove account for a guild. Returns True if existed."""
    config = load_config()
    if str(guild_id) in config.get("accounts", {}):
        del config["accounts"][str(guild_id)]
        save_config(config)
        return True
    return False


def get_all_accounts() -> dict:
    """Get all stored accounts."""
    config = load_config()
    return config.get("accounts", {})


# ==========================================================
# GUILD SETTINGS
# ==========================================================
def get_guild_settings(guild_id: int | None) -> dict:
    """Get per-guild automation settings with defaults."""
    if guild_id is None:
        return dict(DEFAULT_SETTINGS)
    config = load_config()
    guild_settings = config.get("guild_settings", {}).get(str(guild_id), {})
    return {**DEFAULT_SETTINGS, **guild_settings}


def set_guild_setting(guild_id: int, key: str, value: Any) -> None:
    """Update a single guild setting."""
    if key not in DEFAULT_SETTINGS:
        raise KeyError(f"Unknown setting: {key}")
    config = load_config()
    gs = config.setdefault("guild_settings", {}).setdefault(str(guild_id), {})
    gs[key] = value
    save_config(config)


def reset_guild_settings(guild_id: int) -> None:
    """Reset a guild's settings back to defaults."""
    config = load_config()
    if str(guild_id) in config.get("guild_settings", {}):
        del config["guild_settings"][str(guild_id)]
        save_config(config)



# ==========================================================
# ADMIN ACCOUNTS (teacher/admin credentials for ban/unban)
# ==========================================================
def get_admin_account(guild_id: int) -> dict | None:
    """Get admin account config for a guild, or None."""
    config = load_config()
    return config.get("admin_accounts", {}).get(str(guild_id))


def set_admin_account(guild_id: int, username: str, password: str, token: str = "") -> dict:
    """Set admin account credentials for a guild (encrypted)."""
    config = load_config()
    config.setdefault("admin_accounts", {})[str(guild_id)] = {
        "username": username,
        "password": password,
        "token": token,
    }
    save_config(config)
    return config["admin_accounts"][str(guild_id)]


def update_admin_token(guild_id: int, token: str) -> None:
    """Update only the token for an existing admin account."""
    config = load_config()
    acct = config.get("admin_accounts", {}).get(str(guild_id))
    if acct:
        acct["token"] = token
        save_config(config)


def remove_admin_account(guild_id: int) -> bool:
    """Remove admin account for a guild. Returns True if existed."""
    config = load_config()
    if str(guild_id) in config.get("admin_accounts", {}):
        del config["admin_accounts"][str(guild_id)]
        save_config(config)
        return True
    return False

