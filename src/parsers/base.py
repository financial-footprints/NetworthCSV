"""Shared types for bank-specific statement parsers."""

from __future__ import annotations

from typing import Protocol

from src.core.transactions import Transaction

__all__ = ["BankParser", "Transaction"]


class BankParser(Protocol):
    def parse_text(self, text: str, *, source_file: str) -> list[Transaction]: ...
