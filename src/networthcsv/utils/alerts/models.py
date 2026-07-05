"""Alert data models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

DeliverMode = Literal["immediate", "batch"]


class AlertKind(StrEnum):
    FILE_MARKER_MISSING = "file_marker_missing"


@dataclass(frozen=True)
class Alert:
    kind: AlertKind
    message: str
    account: str
    source_file: str
    file_markers: list[str]
