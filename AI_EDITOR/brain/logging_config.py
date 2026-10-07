"""Structured logging configuration for AI_EDITOR."""

from __future__ import annotations

import logging
import re
from typing import Optional


class SecretFilter(logging.Filter):
    """Filter that redacts potential API keys from log output."""

    PATTERNS = [
        re.compile(r'(?i)(api[_-]?key|token|secret|password|auth)[\s=:]+\S+'),
        re.compile(r'sk-[a-zA-Z0-9]{20,}'),
        re.compile(r'Bearer\s+\S+'),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern in self.PATTERNS:
            if pattern.search(msg):
                record.msg = pattern.sub('[REDACTED]', str(record.msg))
                record.args = None
        return True


def setup_logging(
    *,
    level: int = logging.INFO,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """Configure the ai_editor logger with console and optional file output."""
    logger = logging.getLogger("ai_editor")
    logger.setLevel(level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    secret_filter = SecretFilter()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(secret_filter)
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(
            log_file, encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(secret_filter)
        logger.addHandler(file_handler)

    return logger
