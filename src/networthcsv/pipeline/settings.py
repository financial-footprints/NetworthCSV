"""Shared extract-stage settings display."""

from __future__ import annotations

from datetime import date
from pathlib import Path


def format_run_settings_lines(
    *,
    bank: str | None,
    subjects: list[str],
    from_filters: list[str],
    bodies: list[str],
    download_dir: Path,
    start_date: date | None,
    extras: tuple[tuple[str, str], ...] = (),
) -> list[str]:
    lines = ["settings:"]
    if bank:
        lines.append(f"  bank:          {bank}")
    for label, value in extras:
        lines.append(f"  {label + ':':14s}{value}")
    lines.append(f"  subjects:      {subjects!r}")
    if from_filters:
        lines.append(f"  from:          {from_filters!r}")
    if bodies:
        lines.append(f"  bodies:        {bodies!r}")
    lines.append(f"  download_path: {download_dir}")
    if start_date is None:
        lines.append("  start_date:    (all emails)")
    else:
        lines.append(f"  start_date:    {start_date.isoformat()}")
    return lines
