"""Account metadata JSON persistence."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

from networthcsv.pipeline.metadata.build import build_account_metadata
from networthcsv.pipeline.metadata.models import (
    AccountMetadata,
    CoverageGap,
    CoverageSegment,
    PeriodCovered,
    StatementGranularity,
    StatementMetadata,
)
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.account_dates import format_account_date, parse_account_date
from networthcsv.utils.path import account_metadata_path


def metadata_to_dict(metadata: AccountMetadata) -> dict[str, object]:
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


def _require_granularity(value: object) -> StatementGranularity:
    if value not in ("monthly", "annual"):
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


def _require_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"expected bool, got {type(value).__name__}")
    return value


def _require_int(value: object, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int):
        raise ValueError(f"expected int, got {type(value).__name__}")
    return value


def metadata_from_dict(payload: dict[str, object]) -> AccountMetadata:
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
            period_approximate=_require_bool(item.get("period_approximate"), False),
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
                approximate=_require_bool(segment.get("approximate"), False),
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
        approximate_statement_count=_require_int(
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
        statement_count=_require_int(
            payload.get("statement_count"), len(statement_dates)
        ),
        period_covered=period_covered,
        last_fetch_date=_cast_optional_str(payload.get("last_fetch_date")),
    )


def read_last_fetch_date(download_path: Path, account: ResolvedAccount) -> date | None:
    path = account_metadata_path(download_path, account)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return parse_account_date(payload.get("last_fetch_date"), "last_fetch_date")


def write_last_fetch_date(
    download_path: Path,
    account: ResolvedAccount,
    fetch_date: date,
) -> Path:
    path = account_metadata_path(download_path, account)
    formatted = format_account_date(fetch_date)
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            payload = {}
        payload["last_fetch_date"] = formatted
        _ = path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(f"{path.suffix}.tmp")
        _ = temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        _ = temp.replace(path)
        return path
    _ = path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f"{path.suffix}.tmp")
    _ = temp.write_text(
        json.dumps({"last_fetch_date": formatted}, indent=2) + "\n",
        encoding="utf-8",
    )
    _ = temp.replace(path)
    return path


def read_account_metadata(path: Path) -> AccountMetadata | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"metadata must be a JSON object: {path}")
    if "statements" not in payload:
        return None
    return metadata_from_dict(payload)


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
        json.dumps(metadata_to_dict(metadata), indent=2) + "\n",
        encoding="utf-8",
    )
    _ = temp.replace(path)


def refresh_account_metadata(
    download_path: Path,
    account: ResolvedAccount,
) -> Path:
    path = account_metadata_path(download_path, account)
    last_fetch_date = format_account_date(read_last_fetch_date(download_path, account))
    metadata = build_account_metadata(download_path, account)
    if last_fetch_date is not None:
        metadata = replace(metadata, last_fetch_date=last_fetch_date)
    write_account_metadata(path, metadata)
    return path
