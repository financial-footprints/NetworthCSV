"""Shared transaction record type."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Transaction:
    date: date
    description: str
    credited: Decimal
    debited: Decimal
    source_file: str
    ref_no: str | None = None
