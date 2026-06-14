"""Bank-specific statement parsers."""

from __future__ import annotations

from src.parsers.base import BankParser, Transaction
from src.parsers.bob import BobParser
from src.parsers.idfc import IdfcParser
from src.parsers.pnb import PnbParser

_PARSERS: dict[str, BankParser] = {
    "bob": BobParser(),
    "pnb": PnbParser(),
    "idfc": IdfcParser(),
}


def get_parser(bank: str) -> BankParser:
    key = bank.strip().lower()
    parser = _PARSERS.get(key)
    if parser is None:
        known = ", ".join(sorted(_PARSERS))
        raise SystemExit(f"error: unknown bank {bank!r} (known: {known})")
    return parser


__all__ = ["BankParser", "Transaction", "get_parser"]
