"""Shared helpers for NetworthCSV tests."""

from __future__ import annotations

import csv
import io
import json
import os
import zipfile
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from unittest import mock

import pyzipper
from networthcsv.context import RunContext
from networthcsv.pipeline.parse.parse import run
from networthcsv.pipeline.reporter import NullRunReporter
from networthcsv.pipeline.results import ParseAccountResult
from networthcsv.settings import (
    AppSettings,
    ResolvedAccount,
    RunSettings,
    ThunderbirdSource,
    ThunderbirdSourceSettings,
)
from networthcsv.settings.models import UserAccountConfig
from networthcsv.utils.alerts.service import AlertService
from networthcsv.utils.banks import get_handler
from networthcsv.utils.banks.account_matching import AccountMatching
from networthcsv.utils.banks.base import CreditCardHandler
from networthcsv.utils.path import account_fy_dir, fy_folder_name, transactions_csv_name

from fixtures import helpers as _fixture_helpers

FIXTURES_ROOT = _fixture_helpers.FIXTURES_ROOT

DEFAULT_OPENING_DATE = "01-01-2020"
_MISSING_DEFAULT_ENV = Path("/__networthcsv_missing_default_env__")


def default_test_env(root: Path, **overrides: str) -> dict[str, str]:
    env = {
        "DOWNLOAD_PATH": str(root / "statements"),
        "SOURCE_TYPE": "thunderbird",
        "THUNDERBIRD_PROFILE": str(root / "profile"),
        "LOG_LEVEL": "info",
        "ALERTS_TYPE": "console",
    }
    env.update(overrides)
    return env


def write_accounts(directory: Path, accounts: list[dict[str, object]]) -> Path:
    path = directory / "accounts.json"
    _ = path.write_text(json.dumps(accounts), encoding="utf-8")
    return path


def reset_dotenv_state() -> None:
    import networthcsv.settings._load as load_module

    load_module.reset_dotenv_state()


@contextmanager
def test_env(root: Path, **overrides: str) -> Generator[dict[str, str], None, None]:
    import networthcsv.settings._load as load_module

    reset_dotenv_state()
    env = default_test_env(root, **overrides)
    with mock.patch.object(load_module, "_DEFAULT_ENV_PATH", _MISSING_DEFAULT_ENV):
        with mock.patch.dict(os.environ, env, clear=True):
            yield env


@contextmanager
def test_env_with_dotenv_chain(
    root: Path, **overrides: str
) -> Generator[dict[str, str], None, None]:
    """Supplemental env vars while a caller-patched ``_DEFAULT_ENV_PATH`` chain loads."""
    reset_dotenv_state()
    env = default_test_env(root, **overrides)
    with mock.patch.dict(os.environ, env, clear=True):
        yield env


@contextmanager
def isolated_environ(**overrides: str) -> Generator[dict[str, str], None, None]:
    """Set os.environ without loading the repo ``.env`` file."""
    import networthcsv.settings._load as load_module

    reset_dotenv_state()
    env = dict(overrides)
    with mock.patch.object(load_module, "_DEFAULT_ENV_PATH", _MISSING_DEFAULT_ENV):
        with mock.patch.dict(os.environ, env, clear=True):
            yield env


def extract_side_effect(
    mapping: dict[Path, str],
) -> Callable[..., str]:
    def side_effect(
        path: Path,
        _passwords: list[str],
        *,
        annotate_edge_amount_colors: bool = False,
    ) -> str:
        _ = annotate_edge_amount_colors
        return mapping[path]

    return side_effect


def credit_card_handler(bank: str, variant: str | None) -> CreditCardHandler:
    handler = get_handler(bank, variant)
    assert isinstance(handler, CreditCardHandler)
    return handler


def account(
    *,
    bank: str = "bob",
    variant: str | None = "easy",
    text_contains: list[str] | str | None = None,
    text_not_contains: list[str] | str | None = None,
    account_number: str = "5678",
    opening_date: date | str | None = None,
    closing_date: date | str | None = None,
    passwords: list[str] | None = None,
) -> ResolvedAccount:
    handler = get_handler(bank, variant)
    defaults = handler.matching_defaults()
    if text_contains is None:
        statement_text_contains = [account_number]
    elif isinstance(text_contains, list):
        statement_text_contains = text_contains
    else:
        statement_text_contains = [text_contains]
    resolved_passwords = passwords if passwords is not None else ["secret"]
    user_data: dict[str, object] = {
        "bank": bank,
        "variant": variant,
        "account_number": account_number,
        "passwords": resolved_passwords,
        "opening_date": opening_date or DEFAULT_OPENING_DATE,
        "statement": {
            "text_contains": statement_text_contains,
        },
    }
    if closing_date is not None:
        user_data["closing_date"] = closing_date
    if text_not_contains is not None:
        cast_statement = user_data["statement"]
        assert isinstance(cast_statement, dict)
        cast_statement["text_not_contains"] = (
            text_not_contains
            if isinstance(text_not_contains, list)
            else [text_not_contains]
        )
    user = UserAccountConfig.model_validate(user_data)
    matching = AccountMatching.merge(defaults, user)
    resolved: dict[str, object] = {
        "bank": bank,
        "variant": variant,
        "account_number": account_number,
        "passwords": resolved_passwords,
        "opening_date": user.opening_date,
        **matching.model_dump(),
    }
    if user.closing_date is not None:
        resolved["closing_date"] = user.closing_date
    return ResolvedAccount.model_validate(resolved)


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
        settings=AppSettings(
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


def statement_fy_dir(
    download_path: Path,
    account: ResolvedAccount,
    period_stem: str,
) -> Path:
    return account_fy_dir(download_path, account, fy_folder_name(period_stem))


def write_statement_pair(
    download_path: Path,
    account: ResolvedAccount,
    period_stem: str,
    txt_text: str,
) -> Path:
    fy_dir = statement_fy_dir(download_path, account, period_stem)
    _ = fy_dir.mkdir(parents=True, exist_ok=True)
    _ = (fy_dir / f"{period_stem}.pdf").write_bytes(b"%PDF")
    _ = (fy_dir / f"{period_stem}.txt").write_text(txt_text, encoding="utf-8")
    return fy_dir


def write_statement_csv(
    download_path: Path,
    account: ResolvedAccount,
    period_stem: str,
    csv_text: str,
) -> Path:
    fy_dir = statement_fy_dir(download_path, account, period_stem)
    _ = fy_dir.mkdir(parents=True, exist_ok=True)
    csv_path = fy_dir / f"{period_stem}.csv"
    _ = csv_path.write_text(csv_text, encoding="utf-8")
    return csv_path


def run_parse(
    download_path: Path,
    account: ResolvedAccount,
) -> ParseAccountResult:
    return run(account, run_context(download_path))


def transactions_output_path(fy_dir: Path, period_stem: str) -> Path:
    return fy_dir / transactions_csv_name(period_stem)


def read_transactions_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def build_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def build_aes_zip(entries: dict[str, bytes], password: str) -> bytes:
    buffer = io.BytesIO()
    pwd_bytes = password.encode("utf-8")
    with pyzipper.AESZipFile(
        buffer,
        "w",
        compression=pyzipper.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as archive:
        archive.setpassword(pwd_bytes)
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()
