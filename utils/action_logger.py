"""
Structured action logger for tracking user commands and homework completions.

Stores timestamped JSON entries in action_log.json alongside the bot folder.
Supports three query types used by the /logs command:
  - bot:     raw log lines from bot.log
  - user:    command usage history per user
  - homework: homework completion results per user
"""

import json
import os
import time
from pathlib import Path
from typing import Any

LOG_FILE = Path(__file__).resolve().parent.parent / "action_log.json"
MAX_ENTRIES = 2000

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load() -> list[dict]:
    if not LOG_FILE.exists():
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save(entries: list[dict]) -> None:
    """Atomically write the last MAX_ENTRIES to disk."""
    trimmed = entries[-MAX_ENTRIES:]
    tmp = str(LOG_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, indent=2, ensure_ascii=False)
    os.replace(tmp, LOG_FILE)


# ---------------------------------------------------------------------------
# Public write API
# ---------------------------------------------------------------------------

def log_command(
    user_id: int,
    user_name: str,
    command: str,
    details: str = "",
) -> None:
    """Record that a user ran a slash command.

    Args:
        user_id: Discord user ID.
        user_name: Discord display / global name.
        command: Command name (e.g. "login", "homework").
        details: Optional extra context (guild_id, params, etc.).
    """
    entries = _load()
    entries.append({
        "type": "command",
        "user_id": user_id,
        "user_name": user_name,
        "command": command,
        "details": details,
        "timestamp": time.time(),
    })
    _save(entries)


def log_homework_result(
    user_id: int,
    user_name: str,
    homework_name: str,
    tasks_ok: int,
    tasks_total: int,
    guild_id: int,
) -> None:
    """Record a homework completion result.

    Args:
        user_id: Discord user ID.
        user_name: Discord display / global name.
        homework_name: Name of the homework assignment.
        tasks_ok: Number of tasks completed successfully.
        tasks_total: Total number of tasks submitted.
        guild_id: Discord guild (server) ID.
    """
    entries = _load()
    entries.append({
        "type": "homework",
        "user_id": user_id,
        "user_name": user_name,
        "homework_name": homework_name,
        "tasks_ok": tasks_ok,
        "tasks_total": tasks_total,
        "guild_id": guild_id,
        "timestamp": time.time(),
    })
    _save(entries)


def log_message(message: str) -> None:
    """Log a generic status message (used for login/logout events)."""
    entries = _load()
    entries.append({
        "type": "message",
        "text": message,
        "timestamp": time.time(),
    })
    _save(entries)


# ---------------------------------------------------------------------------
# Public read API
# ---------------------------------------------------------------------------

def get_user_commands(user_id: int, limit: int = 25) -> list[dict]:
    """Get recent slash command entries for a user (newest first)."""
    entries = _load()
    relevant = [e for e in entries if e.get("type") == "command" and e.get("user_id") == user_id]
    relevant.reverse()
    return relevant[:limit]


def get_user_homework(user_id: int, limit: int = 20) -> list[dict]:
    """Get recent homework entries for a user (newest first)."""
    entries = _load()
    relevant = [e for e in entries if e.get("type") == "homework" and e.get("user_id") == user_id]
    relevant.reverse()
    return relevant[:limit]


def get_all_users_summary() -> list[dict]:
    """Return a summary of all users that have logged actions."""
    entries = _load()
    seen: dict[int, dict] = {}
    for e in entries:
        uid = e.get("user_id")
        if uid and uid not in seen:
            seen[uid] = {
                "user_id": uid,
                "user_name": e.get("user_name", str(uid)),
                "last_seen": e.get("timestamp", 0),
                "command_count": sum(1 for x in entries if x.get("type") == "command" and x.get("user_id") == uid),
                "homework_count": sum(1 for x in entries if x.get("type") == "homework" and x.get("user_id") == uid),
            }
    return sorted(seen.values(), key=lambda x: x["last_seen"], reverse=True)


def get_bot_log_lines(limit: int = 20) -> list[str]:
    """Read last *limit* lines from the bot log file."""
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_file = log_dir / "bot.log"
    if not log_file.exists():
        return ["[No bot.log found — the bot hasn't logged anything yet.]"]
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [l.rstrip("\n\r") for l in lines[-limit:]]
    except OSError:
        return ["[Failed to read bot.log]"]

