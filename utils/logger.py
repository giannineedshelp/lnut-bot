# utils/logger.py
"""
Logging configuration for lnut-bot.
"""

import logging
import sys
from pathlib import Path

BASE_DIR = Path("/storage/emulated/0/Documents/In_bot/lnut-bot")
LOG_DIR = BASE_DIR / "logs"


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging with both console and file handlers."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_path = LOG_DIR / "lnut_bot.log"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # File handler
    file_handler = logging.FileHandler(
        log_path, encoding="utf-8", mode="a"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    logging.getLogger("lnut_bot").info(
        f"Logging initialized. Log file: {log_path}"
    )