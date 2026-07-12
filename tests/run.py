"""make test entry: silence expected log noise, then unittest discover."""

from __future__ import annotations

import logging
import sys
import unittest

logging.disable(logging.WARNING)
for name in ("pdfminer", "pdfplumber", "pypdf"):
    logging.getLogger(name).setLevel(logging.ERROR)


def main() -> None:
    argv = ["unittest", "discover", "-s", "tests", *sys.argv[1:]]
    unittest.main(module=None, argv=argv)


if __name__ == "__main__":
    main()
