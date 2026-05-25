"""Shared types for bank-specific PDF parsers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Transaction:
    date: date
    description: str
    credited: Decimal
    debited: Decimal
    source_file: str
    ref_no: str | None = None


class BankParser(Protocol):
    def parse_pdf(self, path: Path, password: str | None) -> list[Transaction]: ...
