"""Build and write per-account metadata from canonical statement files on disk."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from networthcsv.context import RunContext
from networthcsv.pipeline.cleanup.statement_period import period_start_from_end
from networthcsv.pipeline.results import MetadataAccountResult
from networthcsv.settings import (
    ResolvedAccount,
    account_download_path,
    format_account_date,
    parse_account_date,
)
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.helpers.amounts import balances_match
from networthcsv.utils.path import (
    account_metadata_path,
    discover_account_fy_dirs,
    iter_statement_csvs,
    iter_statement_pairs,
    statement_csv_path,
    txt_path_for_pdf,
)

from networthcsv.utils.statement_period import (
    YearDisplay,
    covered_months_between,
    is_yearly_period,
    parse_month_period,
    year_key_for_period,
    year_key_label,
    yearly_period_bounds,
)

logger = logging.getLogger(__name__)

StatementGranularity = Literal["monthly", "yearly"]


@dataclass(frozen=True)
class StatementMetadata:
    statement_date: str
    formats: tuple[str, ...]
    opening_balance: str | None = None
    closing_balance: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    period_approximate: bool = False
    granularity: StatementGranularity = "monthly"
    covered_months: tuple[str, ...] = ()
    year_key: str | None = None


@dataclass(frozen=True)
class YearlyStatementSummary:
    year_key: str
    statement_date: str
    label: str
    period_start: str
    period_end: str
    formats: tuple[str, ...]


@dataclass(frozen=True)
class CoverageSegment:
    start: str
    end: str
    approximate: bool = False


@dataclass(frozen=True)
class CoverageGap:
    start: str
    end: str
    balances_match: bool | None = None


@dataclass(frozen=True)
class PeriodCovered:
    start: str | None
    end: str | None
    segments: tuple[CoverageSegment, ...]
    gaps: tuple[CoverageGap, ...]
    months: tuple[str, ...]
    approximate_statement_count: int = 0


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
    if is_yearly_period(statement_date):
        bounds = yearly_period_bounds(statement_date)
        if bounds is None:
            return statement_date
        return bounds[0]
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
    yearly_covered: set[str] = set()
    for statement in statements:
        if statement.granularity == "yearly":
            yearly_covered.update(statement.covered_months)

    monthly_statements = tuple(
        statement for statement in statements if statement.granularity == "monthly"
    )
    if len(monthly_statements) < 2:
        return ()

    sorted_statements = sorted(
        monthly_statements,
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
            gaps.extend(
                BalanceGap(month=month, status=status)
                for month in between
                if month not in yearly_covered
            )
            continue

        if following_covered == _next_month_key(
            previous_covered
        ) and not balances_match(closing, opening, tolerance=tolerance):
            gaps.append(BalanceGap(month=previous_covered, status="discontinuity"))
            gaps.append(BalanceGap(month=following_covered, status="discontinuity"))

    return tuple(gaps)


def _coverage_gap_balances_match(
    statements: tuple[StatementMetadata, ...],
    *,
    segment_before_end: str,
    segment_after_start: str,
    tolerance: Decimal | None,
) -> bool | None:
    previous = next(
        (
            statement
            for statement in statements
            if statement.period_end == segment_before_end
        ),
        None,
    )
    following = next(
        (
            statement
            for statement in statements
            if statement.period_start == segment_after_start
        ),
        None,
    )
    if previous is None or following is None:
        return None
    closing = previous.closing_balance
    opening = following.opening_balance
    if closing is None or opening is None:
        return None
    return balances_match(closing, opening, tolerance=tolerance)


def _statement_period_from_path(path: Path) -> str | None:
    period_id = path.stem
    if parse_month_period(period_id) is not None:
        return period_id
    if is_yearly_period(period_id):
        return period_id
    return None


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


def _format_account_date(value: date) -> str:
    formatted = format_account_date(value)
    if formatted is None:
        raise ValueError("date value is required")
    return formatted


def _parse_account_date(value: str) -> date:
    parsed = parse_account_date(value, "date")
    if parsed is None:
        raise ValueError(f"invalid account date: {value!r}")
    return parsed


def _resolve_statement_period(
    text: str,
    *,
    account: ResolvedAccount,
) -> tuple[str | None, str | None, bool]:
    handler = get_handler(account.bank, account.variant)
    period_start, period_end = handler.get_statement_period(text)
    if period_start is not None and period_end is not None:
        if period_start > period_end:
            period_start, period_end = period_end, period_start
        return (
            _format_account_date(period_start),
            _format_account_date(period_end),
            False,
        )
    if period_end is None:
        return None, None, False
    start_day = handler.period_start_day()
    if start_day is None:
        return None, None, False
    period_start = period_start_from_end(period_end, start_day)
    return _format_account_date(period_start), _format_account_date(period_end), False


def _merge_coverage_periods(
    periods: list[tuple[date, date, bool]],
) -> tuple[list[tuple[date, date, bool]], list[tuple[date, date]]]:
    if not periods:
        return [], []
    sorted_periods = sorted(periods, key=lambda item: item[0])
    segments: list[tuple[date, date, bool]] = []
    gaps: list[tuple[date, date]] = []
    current_start, current_end, current_approximate = sorted_periods[0]
    for start, end, approximate in sorted_periods[1:]:
        if start <= current_end + timedelta(days=1):
            if end > current_end:
                current_end = end
            current_approximate = current_approximate or approximate
            continue
        segments.append((current_start, current_end, current_approximate))
        gap_start = current_end + timedelta(days=1)
        gap_end = start - timedelta(days=1)
        if gap_start <= gap_end:
            gaps.append((gap_start, gap_end))
        current_start, current_end, current_approximate = start, end, approximate
    segments.append((current_start, current_end, current_approximate))
    return segments, gaps


def _build_period_covered(
    statements: tuple[StatementMetadata, ...],
    *,
    tolerance: Decimal | None = None,
) -> PeriodCovered:
    months = tuple(
        sorted(
            {
                *(
                    covered_month(statement.statement_date)
                    for statement in statements
                    if statement.granularity == "monthly"
                ),
                *(
                    month
                    for statement in statements
                    if statement.granularity == "yearly"
                    for month in statement.covered_months
                ),
            }
        )
    )
    periods: list[tuple[date, date, bool]] = []
    approximate_statement_count = 0
    for statement in statements:
        if statement.period_approximate:
            approximate_statement_count += 1
        if statement.period_start is None or statement.period_end is None:
            continue
        periods.append(
            (
                _parse_account_date(statement.period_start),
                _parse_account_date(statement.period_end),
                statement.period_approximate,
            )
        )
    if not periods:
        return PeriodCovered(
            start=None,
            end=None,
            segments=(),
            gaps=(),
            months=months,
            approximate_statement_count=approximate_statement_count,
        )
    merged_segments, merged_gaps = _merge_coverage_periods(periods)
    segments = tuple(
        CoverageSegment(
            start=_format_account_date(start),
            end=_format_account_date(end),
            approximate=approximate,
        )
        for start, end, approximate in merged_segments
    )
    gaps = tuple(
        CoverageGap(
            start=_format_account_date(start),
            end=_format_account_date(end),
            balances_match=_coverage_gap_balances_match(
                statements,
                segment_before_end=_format_account_date(merged_segments[index][1]),
                segment_after_start=_format_account_date(merged_segments[index + 1][0]),
                tolerance=tolerance,
            ),
        )
        for index, (start, end) in enumerate(merged_gaps)
    )
    return PeriodCovered(
        start=segments[0].start,
        end=segments[-1].end,
        segments=segments,
        gaps=gaps,
        months=months,
        approximate_statement_count=approximate_statement_count,
    )


def _has_transactions_csv(download_path: Path, account: ResolvedAccount) -> bool:
    for account_fy_dir in discover_account_fy_dirs(download_path, account):
        if (account_fy_dir / "transactions.csv").is_file():
            return True
    return False


def _extract_statement_balances(
    text: str,
    account: ResolvedAccount,
) -> tuple[str | None, str | None]:
    handler = get_handler(account.bank, account.variant)
    return handler.get_opening_balance(text), handler.get_closing_balance(text)


def build_yearly_statement_summaries(
    statements: tuple[StatementMetadata, ...],
    *,
    year_display: YearDisplay,
) -> tuple[YearlyStatementSummary, ...]:
    summaries: list[YearlyStatementSummary] = []
    for statement in statements:
        if statement.granularity != "yearly":
            continue
        if (
            statement.year_key is None
            or statement.period_start is None
            or statement.period_end is None
        ):
            continue
        summaries.append(
            YearlyStatementSummary(
                year_key=statement.year_key,
                statement_date=statement.statement_date,
                label=year_key_label(
                    statement.year_key,
                    year_display=year_display,
                ),
                period_start=statement.period_start,
                period_end=statement.period_end,
                formats=statement.formats,
            )
        )
    return tuple(summaries)


def build_account_metadata(
    download_path: Path,
    account: ResolvedAccount,
) -> AccountMetadata:
    statements_by_date: dict[str, tuple[Path | None, Path | None, Path | None]] = {}

    for pdf_path, txt_path in iter_statement_pairs(download_path, account):
        statement_date = _statement_period_from_path(pdf_path)
        if statement_date is None:
            continue
        existing = statements_by_date.get(statement_date, (None, None, None))
        statements_by_date[statement_date] = (pdf_path, txt_path, existing[2])

    for csv_path in iter_statement_csvs(download_path, account):
        statement_date = _statement_period_from_path(csv_path)
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
            text = txt_path.read_text(encoding="utf-8")
            opening_balance, closing_balance = _extract_statement_balances(
                text,
                account,
            )
            period_start, period_end, period_approximate = _resolve_statement_period(
                text,
                account=account,
            )
        else:
            opening_balance, closing_balance = None, None
            period_start, period_end, period_approximate = None, None, False

        granularity: StatementGranularity = (
            "yearly" if is_yearly_period(statement_date) else "monthly"
        )
        statement_covered_months: tuple[str, ...] = ()
        year_key: str | None = None
        if granularity == "yearly" and period_start and period_end:
            start_date = _parse_account_date(period_start)
            end_date = _parse_account_date(period_end)
            handler = get_handler(account.bank, account.variant)
            statement_covered_months = covered_months_between(start_date, end_date)
            year_key = year_key_for_period(
                start_date,
                end_date,
                year_display=handler.year_display(),
            )

        statements.append(
            StatementMetadata(
                statement_date=statement_date,
                formats=formats,
                opening_balance=opening_balance,
                closing_balance=closing_balance,
                period_start=period_start,
                period_end=period_end,
                period_approximate=period_approximate,
                granularity=granularity,
                covered_months=statement_covered_months,
                year_key=year_key,
            )
        )

    statement_dates = tuple(item.statement_date for item in statements)

    if _has_transactions_csv(download_path, account):
        account_formats.add("csv")

    handler = get_handler(account.bank, account.variant)
    period_covered = _build_period_covered(
        tuple(statements),
        tolerance=handler.balance_match_tolerance(),
    )

    return AccountMetadata(
        account_number=account.account_number,
        bank=account.bank,
        variant=account.variant,
        account_type=account.account_type,
        opening_date=format_account_date(account.opening_date),
        closing_date=format_account_date(account.closing_date),
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
            "period_start": item.period_start,
            "period_end": item.period_end,
            "period_approximate": item.period_approximate,
            "granularity": item.granularity,
            "covered_months": list(item.covered_months),
            "year_key": item.year_key,
        }
        for item in metadata.statements
    ]
    payload["formats"] = list(metadata.formats)
    payload["statement_dates"] = list(metadata.statement_dates)
    period = metadata.period_covered
    payload["period_covered"] = {
        "start": period.start,
        "end": period.end,
        "segments": [
            {
                "start": segment.start,
                "end": segment.end,
                "approximate": segment.approximate,
            }
            for segment in period.segments
        ],
        "gaps": [
            {
                "start": gap.start,
                "end": gap.end,
                "balances_match": gap.balances_match,
            }
            for gap in period.gaps
        ],
        "months": list(period.months),
        "approximate_statement_count": period.approximate_statement_count,
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
            opening_balance=_cast_optional_str(item.get("opening_balance")),
            closing_balance=_cast_optional_str(item.get("closing_balance")),
            period_start=_cast_optional_str(item.get("period_start")),
            period_end=_cast_optional_str(item.get("period_end")),
            period_approximate=_cast_bool(item.get("period_approximate"), False),
            granularity=_require_granularity(item["granularity"]),
            covered_months=_require_month_tuple(item["covered_months"]),
            year_key=_cast_optional_str(item.get("year_key")),
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
    segments_raw = period_raw.get("segments")
    segments = (
        tuple(
            CoverageSegment(
                start=str(segment["start"]),
                end=str(segment["end"]),
                approximate=_cast_bool(segment.get("approximate"), False),
            )
            for segment in segments_raw
            if isinstance(segment, dict)
        )
        if isinstance(segments_raw, list)
        else ()
    )
    gaps_raw = period_raw.get("gaps")
    gaps = (
        tuple(
            CoverageGap(
                start=str(gap["start"]),
                end=str(gap["end"]),
                balances_match=(
                    bool(gap["balances_match"])
                    if isinstance(gap.get("balances_match"), bool)
                    else None
                ),
            )
            for gap in gaps_raw
            if isinstance(gap, dict)
        )
        if isinstance(gaps_raw, list)
        else ()
    )
    period_covered = PeriodCovered(
        start=_cast_optional_str(period_raw.get("start")),
        end=_cast_optional_str(period_raw.get("end")),
        segments=segments,
        gaps=gaps,
        months=months,
        approximate_statement_count=_cast_int(
            period_raw.get("approximate_statement_count"), 0
        ),
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
        variant=_cast_optional_str(payload.get("variant")),
        account_type=str(payload["account_type"]),
        opening_date=_cast_optional_str(payload.get("opening_date")),
        closing_date=_cast_optional_str(payload.get("closing_date")),
        formats=formats,
        statements=statements,
        statement_dates=statement_dates,
        starting=_cast_optional_str(payload.get("starting")),
        ending=_cast_optional_str(payload.get("ending")),
        statement_count=_cast_int(payload.get("statement_count"), len(statement_dates)),
        period_covered=period_covered,
    )


def _require_granularity(value: object) -> StatementGranularity:
    if value not in ("monthly", "yearly"):
        raise ValueError(f"invalid statement granularity: {value!r}")
    return value


def _require_month_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("covered_months must be a list")
    return tuple(str(month) for month in value)


def _cast_optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _cast_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return bool(value)


def _cast_int(value: object, default: int) -> int:
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
