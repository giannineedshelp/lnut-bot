import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output."""

    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[41m",   # Red background
        "RESET": "\033[0m",
    }

    def format(self, record):
        levelname = record.levelname
        color = self.COLORS.get(levelname, self.COLORS["RESET"])
        reset = self.COLORS["RESET"]
        record.levelname = f"{color}{levelname:<8}{reset}"
        return super().format(record)


def setup_logging() -> logging.Logger:
    """Configure and return the root logger."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger = logging.getLogger("lnut_bot")
    logger.setLevel(logging.DEBUG)

    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_format = ColoredFormatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_dir / "bot.log",
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    return logger