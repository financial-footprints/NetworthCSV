"""Shared CLI helpers for CCParser entry points."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from src.core.accounts import iter_accounts
from src.logging_config import configure_logging
from src.settings import (
    DEFAULT_CONFIG_PATH,
    ENV_CONFIG_VAR,
    AccountSettings,
    Settings,
    load_settings,
    resolve_config_path,
)

__all__ = [
    "add_config_argument",
    "parse_args_with_config",
    "run_stage_main",
]


def add_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help=(
            f"Path to extractor.config.json "
            f"(default: ${ENV_CONFIG_VAR} or {DEFAULT_CONFIG_PATH})"
        ),
    )


def parse_args_with_config(
    description: str,
    *,
    positional_name: str | None = None,
    positional_help: str | None = None,
    extra_arguments: Callable[[argparse.ArgumentParser], None] | None = None,
) -> tuple[Path, str | None]:
    parser = argparse.ArgumentParser(description=description)
    add_config_argument(parser)
    if extra_arguments is not None:
        extra_arguments(parser)
    if positional_name is not None:
        parser.add_argument(
            positional_name,
            nargs="?",
            default=None,
            help=positional_help,
        )
    args = parser.parse_args()
    config_path = resolve_config_path(getattr(args, "config", None))
    positional = getattr(args, positional_name, None) if positional_name else None
    return config_path, positional


def run_stage_main(
    description: str,
    *,
    positional_name: str = "download_dir",
    positional_help: str,
    run_account: Callable[[Path, AccountSettings, Settings], None],
    extra_arguments: Callable[[argparse.ArgumentParser], None] | None = None,
) -> None:
    """Load config and run a stage for one account dir or all configured accounts."""
    configure_logging()
    config_path, download_dir_arg = parse_args_with_config(
        description,
        positional_name=positional_name,
        positional_help=positional_help,
        extra_arguments=extra_arguments,
    )
    settings = load_settings(config_path)

    argv_download_dir: Path | None = None
    if download_dir_arg is not None:
        argv_download_dir = Path(download_dir_arg).expanduser()

    iter_accounts(settings, run_account, download_dir=argv_download_dir)
