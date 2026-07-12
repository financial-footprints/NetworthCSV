"""Private JSON/path loading helpers for app and user config."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

from networthcsv.errors import ConfigError
from pydantic import ValidationError

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "app.config.json"
BASE_APP_CONFIG_FILENAME = "app.config.json"
LOCAL_APP_CONFIG_FILENAME = "app.config.local.json"
CONFIG_ENV_VAR = "NETWORTHCSV_CONFIG"


def resolve_path(value: object, base: Path) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


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
    """Resolve app config path: explicit override, then NETWORTHCSV_CONFIG, then default."""
    if override is not None:
        value = str(override).strip()
        if value:
            return Path(value).expanduser().resolve()

    env_value = os.environ.get(CONFIG_ENV_VAR, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()

    return DEFAULT_CONFIG_PATH.resolve()


def load_json_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ConfigError(f"config not found: {path}")

    with path.open(encoding="utf-8") as fh:
        loaded = cast(object, json.load(fh))
    if not isinstance(loaded, dict):
        raise ConfigError(f"config must be a JSON object: {path}")
    return cast(dict[str, object], loaded)


def deep_merge_dict(
    base: dict[str, object],
    overlay: dict[str, object],
) -> dict[str, object]:
    merged = dict(base)
    for key, overlay_value in overlay.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(overlay_value, dict):
            merged[key] = deep_merge_dict(
                cast(dict[str, object], base_value),
                cast(dict[str, object], overlay_value),
            )
        else:
            merged[key] = overlay_value
    return merged


def is_local_app_config_overlay(path: Path) -> bool:
    return path.name == LOCAL_APP_CONFIG_FILENAME


def load_app_config_data(resolved: Path) -> dict[str, object]:
    if not is_local_app_config_overlay(resolved):
        return load_json_object(resolved)

    base_path = resolved.parent / BASE_APP_CONFIG_FILENAME
    if not base_path.is_file():
        raise ConfigError(f"app config overlay requires base config: {base_path}")

    base_data = load_json_object(base_path)
    overlay_data = load_json_object(resolved)
    return deep_merge_dict(base_data, overlay_data)
