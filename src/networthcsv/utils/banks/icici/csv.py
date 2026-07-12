"""ICICI credit-card CSV statement helpers."""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from networthcsv.settings import ResolvedAccount
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.helpers.dates import parse_date_string
from networthcsv.utils.banks.icici.default import IciciDefaultHandler
from networthcsv.utils.banks.period import PeriodSource, ordered_date_bounds
from networthcsv.utils.billing_period import BillingCycle
from networthcsv.utils.statement_period import (
    calendar_bounds_for_period_key,
    fy_key_from_dates,
    fy_period_bounds,
    is_annual_period,
    month_period_from_filename,
    staging_filename_is_annual,
)
from networthcsv.utils.transactions import Transaction

logger = logging.getLogger(__name__)

_TXN_HEADER = "Transaction Details:"
_MESSAGE_HEADER = "MESSAGE Details:"


@dataclass(frozen=True)
class IciciCsvRow:
    date: date
    description: str
    amount: Decimal
    ref_no: str | None = None


def _parse_amount(raw: str) -> Decimal | None:
    cleaned = raw.strip().replace(",", "").replace('"', "")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_icici_csv_rows(csv_text: str) -> list[IciciCsvRow]:
    """Extract transaction rows from an ICICI credit-card CSV export."""
    lines = csv_text.splitlines()
    start_idx: int | None = None
    end_idx = len(lines)
    for index, line in enumerate(lines):
        stripped = line.strip().strip('"')
        if stripped.startswith(_TXN_HEADER):
            start_idx = index + 1
        if stripped.startswith(_MESSAGE_HEADER):
            end_idx = index
            break
    if start_idx is None:
        return []

    section = "\n".join(lines[start_idx:end_idx])
    reader = csv.reader(io.StringIO(section))
    rows: list[IciciCsvRow] = []
    header_seen = False
    for fields in reader:
        if not fields or not any(field.strip() for field in fields):
            continue
        if not header_seen:
            if fields[0].strip().lower() == "date":
                header_seen = True
            continue

        txn_date = parse_date_string(fields[0])
        if txn_date is None:
            # Card-mask line or other non-transaction row.
            continue

        description = fields[2].strip() if len(fields) > 2 else ""
        amount_raw = ""
        if len(fields) > 6 and fields[6].strip():
            amount_raw = fields[6]
        elif len(fields) > 5:
            amount_raw = fields[5]
        amount = _parse_amount(amount_raw)
        if amount is None:
            continue

        ref_no: str | None = None
        if len(fields) > 1:
            candidate = fields[1].strip()
            # Annual exports use short Sr.No.; monthly use longer refs.
            if candidate and not (candidate.isdigit() and len(candidate) <= 3):
                ref_no = candidate

        rows.append(
            IciciCsvRow(
                date=txn_date,
                description=description,
                amount=amount,
                ref_no=ref_no,
            )
        )
    return rows


def icici_csv_rows_to_transactions(
    rows: list[IciciCsvRow],
    *,
    source_file: str,
) -> list[Transaction]:
    transactions: list[Transaction] = []
    for row in rows:
        if row.amount < 0:
            credited = abs(row.amount)
            debited = Decimal("0")
        else:
            credited = Decimal("0")
            debited = row.amount
        transactions.append(
            Transaction(
                date=row.date,
                description=row.description,
                credited=credited,
                debited=debited,
                source_file=source_file,
                ref_no=row.ref_no,
            )
        )
    return transactions


def _fy_key_from_bounds(start: date, end: date) -> str:
    return fy_key_from_dates(start, end)


def _period_from_content(
    handler: IciciDefaultHandler,
    csv_text: str,
) -> tuple[str, PeriodSource] | None:
    period_start, period_end = handler.get_statement_period(csv_text)
    if period_start is not None and period_end is not None:
        period_start, period_end = ordered_date_bounds(period_start, period_end)
        if (
            period_start.year == period_end.year
            and period_start.month == period_end.month
        ):
            return period_end.strftime("%Y-%m"), "content_date"
        return _fy_key_from_bounds(period_start, period_end), "annual"

    statement_date = handler.get_statement_date(csv_text)
    if statement_date is not None:
        return statement_date.strftime("%Y-%m"), "content_date"
    return None


def _period_from_transactions(
    rows: list[IciciCsvRow],
    *,
    account: ResolvedAccount,
    filename: str,
) -> tuple[str, PeriodSource] | None:
    if not rows:
        return None
    txn_dates = [row.date for row in rows]
    cycle = BillingCycle.from_opening_date(account.opening_date)
    periods = cycle.distinct_periods(txn_dates)
    if staging_filename_is_annual(filename) or len(periods) != 1:
        bounds = cycle.bounds_for_transactions(txn_dates)
        return _fy_key_from_bounds(bounds.start, bounds.end), "annual"
    return cycle.end_month_key(periods[0]), "content_date"


def _period_from_filename(
    filename: str,
    rows: list[IciciCsvRow],
    *,
    account: ResolvedAccount,
) -> tuple[str, PeriodSource] | None:
    # Lazy import avoids upload ↔ icici.csv circular dependency.
    from networthcsv.pipeline.upload import period_from_manual_upload  # noqa: PLC0415

    manual = period_from_manual_upload(filename)
    if manual is not None:
        return manual, "manual"

    fallback = month_period_from_filename(filename)
    if fallback != "unknown-month":
        logger.debug(
            "statement date not found in %s; using filename month %s",
            filename,
            fallback,
        )
        return fallback, "filename_fallback"

    if staging_filename_is_annual(filename) and rows:
        txn_dates = [row.date for row in rows]
        cycle = BillingCycle.from_opening_date(account.opening_date)
        bounds = cycle.bounds_for_transactions(txn_dates)
        return _fy_key_from_bounds(bounds.start, bounds.end), "annual"

    return None


def resolve_icici_csv_period_key_with_source(
    csv_text: str,
    filename: str,
    *,
    account: ResolvedAccount,
) -> tuple[str, PeriodSource]:
    """Classify ICICI CSV as monthly or annual and return period key."""
    handler = get_handler(account.bank, account.variant)
    if not isinstance(handler, IciciDefaultHandler):
        return "unknown-month", "unknown"

    content_period = _period_from_content(handler, csv_text)
    if content_period is not None:
        return content_period

    rows = parse_icici_csv_rows(csv_text)

    if rows:
        txn_period = _period_from_transactions(
            rows,
            account=account,
            filename=filename,
        )
        if txn_period is not None:
            return txn_period

    if not rows:
        logger.warning("no ICICI CSV transactions in %s", filename)

    filename_period = _period_from_filename(filename, rows, account=account)
    if filename_period is not None:
        return filename_period

    return "unknown-month", "unknown"


def resolve_icici_csv_period_bounds(
    csv_text: str,
    *,
    account: ResolvedAccount,
) -> tuple[date | None, date | None]:
    """Return inclusive calendar bounds covered by an ICICI CSV export."""
    handler = get_handler(account.bank, account.variant)
    if not isinstance(handler, IciciDefaultHandler):
        return None, None

    period_key, _source = resolve_icici_csv_period_key_with_source(
        csv_text,
        "",
        account=account,
    )
    if is_annual_period(period_key):
        return fy_period_bounds(period_key)

    period_start, period_end = handler.get_statement_period(csv_text)
    if period_start is not None and period_end is not None:
        period_start, period_end = ordered_date_bounds(period_start, period_end)
        return period_start, period_end

    rows = parse_icici_csv_rows(csv_text)
    if not rows:
        return None, None

    cycle = BillingCycle.from_opening_date(account.opening_date)
    txn_dates = [row.date for row in rows]
    periods = cycle.distinct_periods(txn_dates)
    if periods:
        period = periods[0]
        return period.start, period.end

    bounds = calendar_bounds_for_period_key(period_key)
    if bounds is None:
        return None, None
    return bounds
