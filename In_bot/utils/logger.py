import json
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
USER_LOG_DIR = LOG_DIR / "users"
HOMEWORK_LOG_DIR = LOG_DIR / "homework"

LOG_DIR.mkdir(exist_ok=True)
USER_LOG_DIR.mkdir(parents=True, exist_ok=True)
HOMEWORK_LOG_DIR.mkdir(parents=True, exist_ok=True)


class ColoredFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[41m",
        "RESET": "\033[0m",
    }

    def format(self, record):
        original_levelname = record.levelname
        color = self.COLORS.get(original_levelname, self.COLORS["RESET"])
        reset = self.COLORS["RESET"]
        record.levelname = f"{color}{original_levelname:<8}{reset}"
        formatted = super().format(record)
        record.levelname = original_levelname
        return formatted


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("lnut_bot")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(
        ColoredFormatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    file_handler = RotatingFileHandler(
        LOG_DIR / "bot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


def _append_json_log(path: Path, entry: dict):
    existing = []

    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    existing.append(entry)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)


def log_user_command(user_id: int, command: str, details: str = ""):
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "command": command,
        "details": details,
    }

    _append_json_log(USER_LOG_DIR / f"{user_id}.json", entry)


def log_homework_action(
    user_id: int,
    homework_id: str,
    task_name: str,
    completion_pct: int,
    duration: float = 0,
    xp_gained: int = 0,
):
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "homework_id": homework_id,
        "task_name": task_name,
        "completion_pct": completion_pct,
        "duration_seconds": duration,
        "xp_gained": xp_gained,
    }

    _append_json_log(HOMEWORK_LOG_DIR / f"{user_id}.json", entry)


def fetch_user_logs(user_id: int):
    path = USER_LOG_DIR / f"{user_id}.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_homework_logs(user_id: int):
    path = HOMEWORK_LOG_DIR / f"{user_id}.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_bot_logs(level: str = None, lines: int = 100):
    bot_log = LOG_DIR / "bot.log"

    if not bot_log.exists():
        return []

    with open(bot_log, "r", encoding="utf-8") as f:
        all_lines = f.readlines()

    if level:
        level = level.upper()
        all_lines = [line for line in all_lines if f"| {level}" in line]

    return all_lines[-lines:]


def get_user_usage_count(user_id: int) -> int:
    """Return total command count for this user."""
    logs = fetch_user_logs(user_id)
    return len(logs)


