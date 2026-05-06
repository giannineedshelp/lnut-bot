import json
import os
from pathlib import Path

CONFIG_PATH = Path("config.json")


def load_config() -> dict:
    """Load the config file, creating it if it doesn't exist."""
    if not CONFIG_PATH.exists():
        default = {"accounts": {}}
        save_config(default)
        return default
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        default = {"accounts": {}}
        save_config(default)
        return default


def save_config(config: dict) -> None:
    """Save config to disk."""
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def get_account(guild_id: int) -> dict | None:
    """Get account config for a guild, or None."""
    config = load_config()
    return config.get("accounts", {}).get(str(guild_id))


def set_account(guild_id: int, username: str, password: str, token: str = "") -> dict:
    """Set account credentials for a guild."""
    config = load_config()
    if "accounts" not in config:
        config["accounts"] = {}
    config["accounts"][str(guild_id)] = {
        "username": username,
        "password": password,
        "token": token,
    }
    save_config(config)
    return config["accounts"][str(guild_id)]


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


def get_guild_settings(guild_id: int) -> dict:
    """Get per-guild automation settings with defaults."""
    config = load_config()
    defaults = {
        "speed": 10.0,
        "min_accuracy": 85,
        "max_accuracy": 92,
        "stealth_enabled": True,
        "concurrency": 3,
    }
    guild_settings = config.get("guild_settings", {}).get(str(guild_id), {})
    return {**defaults, **guild_settings}


def set_guild_setting(guild_id: int, key: str, value) -> None:
    """Update a single guild setting."""
    config = load_config()
    if "guild_settings" not in config:
        config["guild_settings"] = {}
    if str(guild_id) not in config["guild_settings"]:
        config["guild_settings"][str(guild_id)] = {}
    config["guild_settings"][str(guild_id)][key] = value
    save_config(config)