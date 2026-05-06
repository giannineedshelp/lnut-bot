import logging
from colorama import init, Fore, Style

init(autoreset=True)


class ColorFormatter(logging.Formatter):
    COLORS = {
        "INFO": Fore.CYAN,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "DEBUG": Fore.MAGENTA,
    }

    def format(self, record):
        color = self.COLORS.get(record.levelname, Fore.WHITE)
        msg = super().format(record)
        return f"{color}{msg}{Style.RESET_ALL}"


def setup_logging():
    logger = logging.getLogger("lnut_bot")
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()

    formatter = ColorFormatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(handler)

    return logger