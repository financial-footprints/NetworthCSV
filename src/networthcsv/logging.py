"""CLI logging setup: INFO and below on stdout, WARNING+ on stderr."""

from __future__ import annotations

import logging
import sys
from typing import Literal

from typing_extensions import override

LogLevel = Literal["debug", "info"]


class _MaxLevelFilter(logging.Filter):
    _max_level: int

    def __init__(self, max_level: int) -> None:
        super().__init__()
        self._max_level = max_level

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self._max_level


def configure_logging(log_level: LogLevel = "info") -> None:
    level = logging.DEBUG if log_level == "debug" else logging.INFO
    root = logging.getLogger()
    if not root.handlers:
        formatter = logging.Formatter("%(message)s")

        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(logging.DEBUG)
        stdout_handler.addFilter(_MaxLevelFilter(logging.INFO))
        stdout_handler.setFormatter(formatter)

        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.WARNING)
        stderr_handler.setFormatter(formatter)

        root.addHandler(stdout_handler)
        root.addHandler(stderr_handler)

        for name in ("pdfminer", "pdfplumber"):
            logging.getLogger(name).setLevel(logging.WARNING)
        logging.getLogger("pypdf").setLevel(logging.ERROR)

    root.setLevel(level)
