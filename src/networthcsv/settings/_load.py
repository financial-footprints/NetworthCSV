"""Private JSON/path loading helpers for accounts config."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

from dotenv import dotenv_values
from networthcsv.errors import ConfigError
from pydantic import ValidationError

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_ENV_PATH = _PROJECT_ROOT / ".env"
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "accounts.json"
CONFIG_ENV_VAR = "ACCOUNT_CONFIG_PATH"
ENV_PATH_VAR = "ENV_NETWORTHCSV"
ENV_PATH_KEY = "ENV_PATH"
_MAX_ENV_PATH_DEPTH = 10
_dotenv_loaded = False


def project_root() -> Path:
    return _PROJECT_ROOT


def resolve_path(value: object, base: Path) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


def _resolve_env_start(override: str | Path | None = None) -> Path:
    if override is not None:
        value = str(override).strip()
        if value:
            return Path(value).expanduser().resolve()

    env_value = os.environ.get(ENV_PATH_VAR, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()

    return _DEFAULT_ENV_PATH.resolve()


def _load_env_chain(start: Path) -> Path | None:
    """Load ``start`` and follow ``ENV_PATH`` hops. Returns leaf path, or None if missing."""
    if not start.is_file():
        return None

    merged: dict[str, str] = {}
    leaf = start.resolve()
    for _ in range(_MAX_ENV_PATH_DEPTH):
        values = dotenv_values(leaf)
        for key, value in values.items():
            if key != ENV_PATH_KEY and value is not None:
                merged[key] = value
        hop = (values.get(ENV_PATH_KEY) or "").strip()
        if not hop:
            os.environ.update(merged)
            return leaf
        leaf = resolve_path(hop, leaf.parent)

    raise ConfigError(f"ENV_PATH chain exceeds maximum depth of {_MAX_ENV_PATH_DEPTH}")


def reset_dotenv_state() -> None:
    global _dotenv_loaded
    _dotenv_loaded = False


def _ensure_dotenv_loaded() -> None:
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _ = _load_env_chain(_resolve_env_start())
    _dotenv_loaded = True


def format_exception(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts: list[str] = []
        for error in exc.errors():
            loc = ".".join(str(part) for part in error["loc"])
            parts.append(f"{loc}: {error['msg']}")
        return "; ".join(parts)
    return str(exc)


def config_error(
    config_path: Path,
    exc: Exception,
    *,
    context: str = "",
) -> ConfigError:
    detail = format_exception(exc)
    message = f"invalid config {config_path}"
    if context:
        message = f"{message} ({context})"
    return ConfigError(f"{message}: {detail}")


def resolve_config_path(override: str | Path | None = None) -> Path:
    """Resolve accounts config path: explicit override, then ACCOUNT_CONFIG_PATH, then default."""
    _ensure_dotenv_loaded()

    if override is not None:
        value = str(override).strip()
        if value:
            return Path(value).expanduser().resolve()

    env_value = os.environ.get(CONFIG_ENV_VAR, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()

    return DEFAULT_CONFIG_PATH.resolve()


def load_accounts_json(path: Path) -> list[object]:
    if not path.is_file():
        raise ConfigError(f"config not found: {path}")

    with path.open(encoding="utf-8") as fh:
        loaded = cast(object, json.load(fh))
    if not isinstance(loaded, list):
        raise ConfigError(f"accounts config must be a JSON array: {path}")
    return cast(list[object], loaded)
