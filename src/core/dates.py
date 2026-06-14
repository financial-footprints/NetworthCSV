"""Shared date parsing for bank statement text."""

from __future__ import annotations

from datetime import date, datetime


def parse_date_dmy_slash(raw: str) -> date | None:
    try:
        return datetime.strptime(raw, "%d/%m/%Y").date()
    except ValueError:
        return None


def parse_date_dmy_mon(raw: str) -> date | None:
    normalised = raw[:3] + raw[3:6].title() + raw[6:]
    try:
        return datetime.strptime(normalised, "%d-%b-%Y").date()
    except ValueError:
        return None


def parse_date_dmy_mon_short(raw: str) -> date | None:
    normalised = raw[:3] + raw[3:6].title() + raw[6:]
    try:
        return datetime.strptime(normalised, "%d %b %y").date()
    except ValueError:
        return None
