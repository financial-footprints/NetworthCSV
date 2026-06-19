"""Alert data models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

DeliverMode = Literal["immediate", "batch"]


class AlertKind(StrEnum):
    IDENTIFIER_MISSING = "identifier_missing"


@dataclass(frozen=True)
class Alert:
    kind: AlertKind
    message: str
    account: str
    source_file: str
    identifier: str
