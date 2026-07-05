"""Build and write per-account metadata from canonical statement files on disk."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from networthcsv.context import RunContext
from networthcsv.pipeline.results import MetadataAccountResult
from networthcsv.settings import (
    ResolvedAccount,
    account_download_path,
    format_account_month_date,
    format_opening_date,
)
from networthcsv.pipeline.metadata.statement_balance import (
    balances_match,
    extract_closing_balance,
    extract_opening_balance,
)
from networthcsv.utils.path import (
    account_metadata_path,
    discover_account_fy_dirs,
    iter_statement_csvs,
    iter_statement_pairs,
    statement_csv_path,
    txt_path_for_pdf,
)

logger = logging.getLogger(__name__)

_MONTH_STEM_PATTERN = re.compile(r"^(\d{4}-\d{2})$")


@dataclass(frozen=True)
class StatementMetadata:
    statement_date: str
    formats: tuple[str, ...]
    opening_balance: str | None = None
    closing_balance: str | None = None


@dataclass(frozen=True)
class PeriodCovered:
    start: str | None
    end: str | None
    months: tuple[str, ...]


BalanceGapStatus = Literal["matched", "mismatched", "discontinuity"]


@dataclass(frozen=True)
class BalanceGap:
    month: str
    status: BalanceGapStatus


@dataclass(frozen=True)
class AccountMetadata:
    account_number: str
    bank: str
    variant: str | None
    account_type: str
    opening_date: str | None
    closing_date: str | None
    formats: tuple[str, ...]
    statements: tuple[StatementMetadata, ...]
    statement_dates: tuple[str, ...]
    starting: str | None
    ending: str | None
    statement_count: int
    period_covered: PeriodCovered


def covered_month(statement_date: str) -> str:
    year_str, month_str = statement_date.split("-", 1)
    year = int(year_str)
    month = int(month_str)
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def statement_date_for_covered_month(covered: str) -> str:
    return _next_month_key(covered)


def _next_month_key(month: str) -> str:
    year_str, month_str = month.split("-", 1)
    year = int(year_str)
    month_num = int(month_str)
    if month_num == 12:
        return f"{year + 1}-01"
    return f"{year}-{month_num + 1:02d}"


def months_between_exclusive(start: str, end: str) -> tuple[str, ...]:
    """Return YYYY-MM covered-month keys strictly between start and end."""
    if start >= end:
        return ()
    months: list[str] = []
    current = _next_month_key(start)
    while current < end:
        months.append(current)
        current = _next_month_key(current)
    return tuple(months)


def compute_balance_gaps(
    statements: tuple[StatementMetadata, ...],
    *,
    tolerance: Decimal | None = None,
) -> tuple[BalanceGap, ...]:
    """Mark gap months and adjacent-statement balance discontinuities."""
    if len(statements) < 2:
        return ()

    sorted_statements = sorted(
        statements,
        key=lambda item: covered_month(item.statement_date),
    )
    gaps: list[BalanceGap] = []
    for index in range(len(sorted_statements) - 1):
        previous = sorted_statements[index]
        following = sorted_statements[index + 1]
        previous_covered = covered_month(previous.statement_date)
        following_covered = covered_month(following.statement_date)
        between = months_between_exclusive(previous_covered, following_covered)

        closing = previous.closing_balance
        opening = following.opening_balance
        if closing is None or opening is None:
            continue

        if between:
            status: BalanceGapStatus = (
                "matched"
                if balances_match(closing, opening, tolerance=tolerance)
                else "mismatched"
            )
            gaps.extend(BalanceGap(month=month, status=status) for month in between)
            continue

        if following_covered == _next_month_key(
            previous_covered
        ) and not balances_match(closing, opening, tolerance=tolerance):
            gaps.append(BalanceGap(month=previous_covered, status="discontinuity"))
            gaps.append(BalanceGap(month=following_covered, status="discontinuity"))

    return tuple(gaps)


def _month_stem_from_path(path: Path) -> str | None:
    match = _MONTH_STEM_PATTERN.fullmatch(path.stem)
    if match is None:
        return None
    return match.group(1)


def _statement_formats(
    pdf_path: Path | None,
    txt_path: Path | None,
    csv_path: Path | None,
) -> tuple[str, ...]:
    formats: list[str] = []
    if pdf_path is not None and pdf_path.is_file():
        formats.append("pdf")
    if txt_path is not None and txt_path.is_file():
        formats.append("txt")
    if csv_path is not None and csv_path.is_file():
        formats.append("csv")
    return tuple(formats)


def _build_period_covered(statement_dates: tuple[str, ...]) -> PeriodCovered:
    months = tuple(
        sorted({covered_month(statement_date) for statement_date in statement_dates})
    )
    if not months:
        return PeriodCovered(start=None, end=None, months=())
    return PeriodCovered(start=months[0], end=months[-1], months=months)


def _has_transactions_csv(download_path: Path, account: ResolvedAccount) -> bool:
    for account_fy_dir in discover_account_fy_dirs(download_path, account):
        if (account_fy_dir / "transactions.csv").is_file():
            return True
    return False


def _extract_statement_balances(
    txt_path: Path,
    account: ResolvedAccount,
) -> tuple[str | None, str | None]:
    if not txt_path.is_file():
        return None, None
    text = txt_path.read_text(encoding="utf-8")
    opening_markers = tuple(account.metadata.balances.opening)
    closing_markers = tuple(account.metadata.balances.closing)
    opening = (
        extract_opening_balance(text, opening_markers) if opening_markers else None
    )
    closing = (
        extract_closing_balance(text, closing_markers) if closing_markers else None
    )
    return opening, closing


def build_account_metadata(
    download_path: Path,
    account: ResolvedAccount,
) -> AccountMetadata:
    statements_by_date: dict[str, tuple[Path | None, Path | None, Path | None]] = {}

    for pdf_path, txt_path in iter_statement_pairs(download_path, account):
        statement_date = _month_stem_from_path(pdf_path)
        if statement_date is None:
            continue
        existing = statements_by_date.get(statement_date, (None, None, None))
        statements_by_date[statement_date] = (pdf_path, txt_path, existing[2])

    for csv_path in iter_statement_csvs(download_path, account):
        statement_date = _month_stem_from_path(csv_path)
        if statement_date is None:
            continue
        existing = statements_by_date.get(statement_date, (None, None, None))
        statements_by_date[statement_date] = (existing[0], existing[1], csv_path)

    statements: list[StatementMetadata] = []
    account_formats: set[str] = set()

    for statement_date in sorted(statements_by_date):
        pdf_path, txt_path, csv_path = statements_by_date[statement_date]
        if txt_path is None and pdf_path is not None:
            txt_path = txt_path_for_pdf(pdf_path)
        if csv_path is None:
            csv_path = statement_csv_path(download_path, account, statement_date)
        formats = _statement_formats(pdf_path, txt_path, csv_path)
        if not formats:
            continue
        account_formats.update(formats)
        if txt_path is not None and txt_path.is_file():
            opening_balance, closing_balance = _extract_statement_balances(
                txt_path,
                account,
            )
        else:
            opening_balance, closing_balance = None, None
        statements.append(
            StatementMetadata(
                statement_date=statement_date,
                formats=formats,
                opening_balance=opening_balance,
                closing_balance=closing_balance,
            )
        )

    statement_dates = tuple(item.statement_date for item in statements)

    if _has_transactions_csv(download_path, account):
        account_formats.add("csv")

    period_covered = _build_period_covered(statement_dates)

    return AccountMetadata(
        account_number=account.account_number,
        bank=account.bank,
        variant=account.variant,
        account_type=account.account_type,
        opening_date=format_opening_date(account.opening_date),
        closing_date=format_account_month_date(account.closing_date),
        formats=tuple(sorted(account_formats)),
        statements=tuple(statements),
        statement_dates=statement_dates,
        starting=statement_dates[0] if statement_dates else None,
        ending=statement_dates[-1] if statement_dates else None,
        statement_count=len(statement_dates),
        period_covered=period_covered,
    )


def _metadata_to_dict(metadata: AccountMetadata) -> dict[str, object]:
    payload = asdict(metadata)
    payload["statements"] = [
        {
            "statement_date": item.statement_date,
            "formats": list(item.formats),
            "opening_balance": item.opening_balance,
            "closing_balance": item.closing_balance,
        }
        for item in metadata.statements
    ]
    payload["formats"] = list(metadata.formats)
    payload["statement_dates"] = list(metadata.statement_dates)
    period = metadata.period_covered
    payload["period_covered"] = {
        "start": period.start,
        "end": period.end,
        "months": list(period.months),
    }
    return payload


def _metadata_from_dict(payload: dict[str, object]) -> AccountMetadata:
    statements_raw = payload.get("statements")
    if not isinstance(statements_raw, list):
        raise ValueError("metadata statements must be a list")
    statements = tuple(
        StatementMetadata(
            statement_date=str(item["statement_date"]),
            formats=tuple(str(fmt) for fmt in item["formats"]),
            opening_balance=cast_optional_str(item.get("opening_balance")),
            closing_balance=cast_optional_str(item.get("closing_balance")),
        )
        for item in statements_raw
        if isinstance(item, dict)
    )
    period_raw = payload.get("period_covered")
    if not isinstance(period_raw, dict):
        raise ValueError("metadata period_covered must be an object")
    months_raw = period_raw.get("months")
    months = (
        tuple(str(month) for month in months_raw)
        if isinstance(months_raw, list)
        else ()
    )
    period_covered = PeriodCovered(
        start=cast_optional_str(period_raw.get("start")),
        end=cast_optional_str(period_raw.get("end")),
        months=months,
    )
    formats_raw = payload.get("formats")
    formats = (
        tuple(str(fmt) for fmt in formats_raw) if isinstance(formats_raw, list) else ()
    )
    statement_dates_raw = payload.get("statement_dates")
    statement_dates = (
        tuple(str(item) for item in statement_dates_raw)
        if isinstance(statement_dates_raw, list)
        else ()
    )
    return AccountMetadata(
        account_number=str(payload["account_number"]),
        bank=str(payload["bank"]),
        variant=cast_optional_str(payload.get("variant")),
        account_type=str(payload["account_type"]),
        opening_date=cast_optional_str(payload.get("opening_date")),
        closing_date=cast_optional_str(payload.get("closing_date")),
        formats=formats,
        statements=statements,
        statement_dates=statement_dates,
        starting=cast_optional_str(payload.get("starting")),
        ending=cast_optional_str(payload.get("ending")),
        statement_count=cast_int(payload.get("statement_count"), len(statement_dates)),
        period_covered=period_covered,
    )


def cast_optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def cast_int(value: object, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return int(str(value))


def read_account_metadata(path: Path) -> AccountMetadata | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"metadata must be a JSON object: {path}")
    return _metadata_from_dict(payload)


def load_account_metadata(
    download_path: Path,
    account: ResolvedAccount,
) -> tuple[AccountMetadata, bool]:
    path = account_metadata_path(download_path, account)
    metadata = read_account_metadata(path)
    if metadata is not None:
        return metadata, True
    return build_account_metadata(download_path, account), False


def write_account_metadata(path: Path, metadata: AccountMetadata) -> None:
    _ = path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f"{path.suffix}.tmp")
    _ = temp.write_text(
        json.dumps(_metadata_to_dict(metadata), indent=2) + "\n",
        encoding="utf-8",
    )
    _ = temp.replace(path)


def refresh_account_metadata(
    download_path: Path,
    account: ResolvedAccount,
) -> Path:
    metadata = build_account_metadata(download_path, account)
    path = account_metadata_path(download_path, account)
    write_account_metadata(path, metadata)
    return path


def run(
    account: ResolvedAccount,
    ctx: RunContext,
) -> MetadataAccountResult:
    staging_dir = account_download_path(ctx.settings, account)
    ctx.reporter.metadata_started(account.bank, staging_dir)

    metadata = build_account_metadata(ctx.settings.download_path, account)
    output = account_metadata_path(ctx.settings.download_path, account)
    write_account_metadata(output, metadata)
    logger.debug("wrote metadata: %s", output)

    result = MetadataAccountResult(
        bank=account.bank,
        download_dir=staging_dir,
        output=output,
        statement_count=metadata.statement_count,
    )
    ctx.reporter.metadata_done(result)
    return result


def run_account(ctx: RunContext, account: ResolvedAccount) -> MetadataAccountResult:
    return run(account, ctx)


def main() -> None:
    from networthcsv.cli import cli_main, run_stage_main

    cli_main(lambda: run_stage_main(run_account=run_account))


if __name__ == "__main__":
    main()
