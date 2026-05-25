"""Load settings from extractor.config.json and environment."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_SCRIPT_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = _SCRIPT_DIR / "extractor.config.json"


@dataclass
class Settings:
    profile: Path
    subject: str
    download_path: Path
    mbox: Path | None
    pdf_password: str | None
    bank: str
    create_combined_csv: bool


def _resolve_path(value: str | Path, base: Path) -> Path:
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = (base / p).resolve()
    return p


def _load_pdf_password(data: dict[str, object]) -> str | None:
    env_password = os.environ.get("PDF_PASSWORD", "").strip()
    if env_password:
        return env_password
    json_password = str(data.get("pdf_password") or "").strip()
    return json_password or None


def load_settings() -> Settings:
    base = _SCRIPT_DIR
    config_path = _CONFIG_PATH
    if not config_path.is_file():
        raise SystemExit(f"error: config not found: {config_path}")

    with config_path.open(encoding="utf-8") as fh:
        loaded: object = cast(object, json.load(fh))
    if not isinstance(loaded, dict):
        raise SystemExit(f"error: config must be a JSON object: {config_path}")
    data = cast(dict[str, object], loaded)

    subject = str(data.get("subject") or "").strip()
    if not subject:
        raise SystemExit(f"error: subject is required in {config_path}")

    profile_raw = data.get("profile")
    download_raw = data.get("download_path")
    if not profile_raw:
        raise SystemExit(f"error: profile is required in {config_path}")
    if not download_raw:
        raise SystemExit(f"error: download_path is required in {config_path}")

    profile = _resolve_path(str(profile_raw), base)
    download_path = _resolve_path(str(download_raw), base)
    mbox_raw = data.get("mbox")
    mbox = _resolve_path(str(mbox_raw), base) if mbox_raw else None
    bank = str(data.get("bank") or "").strip().lower()
    if not bank:
        raise SystemExit(f"error: bank is required in {config_path}")
    create_combined_csv = bool(data.get("create_combined_csv", False))

    return Settings(
        profile=profile,
        subject=subject,
        download_path=download_path,
        mbox=mbox,
        pdf_password=_load_pdf_password(data),
        bank=bank,
        create_combined_csv=create_combined_csv,
    )


def require_pdf_password(settings: Settings) -> str:
    if not settings.pdf_password:
        raise SystemExit(
            "error: PDF password not set (use PDF_PASSWORD env or pdf_password in config)"
        )
    return settings.pdf_password
