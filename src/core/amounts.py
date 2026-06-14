"""Transaction amount parsing and deduplication."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.core.transactions import Transaction


def parse_amount(raw: str, is_credit: bool) -> tuple[Decimal, Decimal]:
    amount = Decimal(raw.replace(",", ""))
    if is_credit:
        return amount, Decimal(0)
    return Decimal(0), amount


def make_transaction(
    txn_date: date,
    description: str,
    amount_raw: str,
    is_credit: bool,
    source_file: str,
    *,
    ref_no: str | None = None,
) -> Transaction:
    credited, debited = parse_amount(amount_raw, is_credit)
    return Transaction(
        date=txn_date,
        description=description.strip(),
        credited=credited,
        debited=debited,
        source_file=source_file,
        ref_no=ref_no,
    )


def _transaction_key(txn: Transaction) -> tuple[object, ...]:
    return (
        txn.date,
        txn.description,
        txn.credited,
        txn.debited,
        txn.source_file,
        txn.ref_no,
    )


def dedupe_transactions(transactions: list[Transaction]) -> list[Transaction]:
    seen: set[tuple[object, ...]] = set()
    unique: list[Transaction] = []
    for txn in transactions:
        key = _transaction_key(txn)
        if key not in seen:
            seen.add(key)
            unique.append(txn)
    return unique
