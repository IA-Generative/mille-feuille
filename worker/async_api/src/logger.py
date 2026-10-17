import logging
import sys
from typing import Any

from loguru import logger

from src.config import settings


class InterceptHandler(logging.Handler):
    """Redirige les logs stdlib vers loguru (même journal que les modules d'async-api)."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _formatter(record: dict[str, Any]) -> str:
    time_str = record["time"].strftime("%Y-%m-%d %H:%M:%S")
    level_str = f"{record['level'].name:<8}"
    name = record["name"]
    function = str(record["function"]).replace("<", "\\<").replace(">", "\\>")
    line = record["line"]

    base = (
        f"<green>{time_str}</green> | "
        f"<level>{level_str}</level> | "
        f"<yellow>{name}</yellow>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"
    )

    extras = " | ".join(f"{k}={v}" for k, v in record["extra"].items())
    message = str(record["message"]).replace("{", "{{").replace("}", "}}").replace("<", "\\<")

    if extras:
        return f"{base} | {extras} | <level>{message}</level> {{exception}}\n"
    return f"{base} | <level>{message}</level> {{exception}}\n"


def _setup_logging() -> None:
    log_level = settings.LOG_LEVEL.upper()
    stdlib_level = getattr(logging, log_level, logging.INFO)

    logger.remove()
    logger.add(sys.stdout, level=log_level, format=_formatter, colorize=True)  # type: ignore[arg-type]  # ty:ignore[no-matching-overload]

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    _loggers_to_intercept = [
        "",
        "aio_pika",
        "aiormq",
        "botocore",
        "boto3",
        "s3transfer",
        "urllib3",
        "httpx",
        "httpcore",
    ]
    for name in _loggers_to_intercept:
        lg = logging.getLogger(name)
        lg.handlers = [InterceptHandler()]
        lg.propagate = False
        # Loggers bruités : limités à WARNING minimum. `httpx` journalise chaque requête en INFO
        # avec son URL : inutile ici, et une URL d'API n'a rien à faire dans un journal de pont.
        if name in ("botocore", "boto3", "s3transfer", "urllib3", "httpx", "httpcore"):
            lg.setLevel(max(stdlib_level, logging.WARNING))
        else:
            lg.setLevel(stdlib_level)


_setup_logging()
