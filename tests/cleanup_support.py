"""Shared helpers for cleanup pipeline tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from networthcsv.context import RunContext
from networthcsv.pipeline.reporter import NullRunReporter
from networthcsv.settings import (
    ResolvedAccount,
    RunSettings,
    Settings,
    ThunderbirdSource,
    ThunderbirdSourceSettings,
)
from networthcsv.utils.alerts.service import AlertService
from networthcsv.utils.banks import get_handler

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"


def extract_side_effect(
    mapping: dict[Path, str],
) -> Callable[[Path, list[str]], str]:
    def side_effect(path: Path, _passwords: list[str]) -> str:
        return mapping[path]

    return side_effect


def account(
    *,
    bank: str = "bob",
    variant: str | None = "easy",
    text_contains: list[str] | str = "5678",
    text_not_contains: list[str] | str | None = None,
    account_number: str = "5678",
) -> ResolvedAccount:
    handler = get_handler(bank, variant)
    defaults = handler.matching_defaults()
    statement_text_contains = (
        text_contains if isinstance(text_contains, list) else [text_contains]
    )
    statement: dict[str, object] = {
        **defaults.model_dump()["statement"],
        "text_contains": statement_text_contains,
    }
    if text_not_contains is not None:
        statement["text_not_contains"] = (
            text_not_contains
            if isinstance(text_not_contains, list)
            else [text_not_contains]
        )
    payload = defaults.model_dump()
    payload["statement"] = statement
    return ResolvedAccount.model_validate(
        {
            "bank": bank,
            "variant": variant,
            "account_number": account_number,
            "passwords": ["secret"],
            **payload,
        }
    )


def staging_layout(
    tmp: str, resolved_account: ResolvedAccount | None = None
) -> tuple[Path, Path, ResolvedAccount]:
    download_path = Path(tmp)
    resolved = resolved_account or account()
    staging_dir = download_path / "credit_card" / resolved.account_number
    _ = staging_dir.mkdir(parents=True, exist_ok=True)
    return staging_dir, download_path, resolved


def run_context(download_path: Path) -> RunContext:
    return RunContext(
        settings=Settings(
            source=ThunderbirdSource(
                thunderbird=ThunderbirdSourceSettings(profile=Path("."))
            ),
            download_path=download_path,
            accounts=[],
            alerts=None,
            run=RunSettings(),
        ),
        alerts=AlertService(handler=None),
        reporter=NullRunReporter(),
    )
