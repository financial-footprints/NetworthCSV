"""Alert data models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

DeliverMode = Literal["immediate", "batch"]


class AlertKind(StrEnum):
    TEXT_CONTAINS_MISSING = "text_contains_missing"
    AMBIGUOUS_STATEMENT_PERIOD = "ambiguous_statement_period"


@dataclass(frozen=True)
class Alert:
    kind: AlertKind
    message: str
    account: str
    source_file: str
    text_contains: list[str]
