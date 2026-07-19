"""Run the test suite: ``uv run python -m tests``."""

from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent

logging.disable(logging.WARNING)
for name in ("pdfminer", "pdfplumber", "pypdf"):
    logging.getLogger(name).setLevel(logging.ERROR)


def main() -> None:
    argv = ["unittest", "discover", "-s", str(_TESTS_DIR), *sys.argv[1:]]
    unittest.main(module=None, argv=argv)


if __name__ == "__main__":
    main()
