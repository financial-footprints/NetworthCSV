"""PNB PDF layout detection and version handlers."""

from __future__ import annotations

from typing import Literal

from networthcsv.utils.banks.pnb.common import (
    INVOICE_NO_LABEL,
    MARKETING_MARKERS,
    V1_INVOICE_NO_MAX_OFFSET,
    V2_INVOICE_NO_MIN_OFFSET,
)
from networthcsv.utils.banks.pnb.default.version1 import LayoutV1
from networthcsv.utils.banks.pnb.default.version2 import LayoutV2

LayoutVersion = Literal["v1", "v2"]

_LAYOUT_V1 = LayoutV1()
_LAYOUT_V2 = LayoutV2()


def detect_layout(text: str) -> LayoutVersion:
    """Pick PDF layout version from raw or sanitized statement text."""
    invoice_idx = text.find(INVOICE_NO_LABEL)
    if invoice_idx == -1:
        return "v1"

    prefix = text[:invoice_idx]
    if any(marker in prefix for marker in MARKETING_MARKERS):
        return "v2"

    if invoice_idx >= V2_INVOICE_NO_MIN_OFFSET:
        return "v2"

    if invoice_idx <= V1_INVOICE_NO_MAX_OFFSET:
        return "v1"

    return "v1"


def get_layout(text: str) -> LayoutV1 | LayoutV2:
    if detect_layout(text) == "v2":
        return _LAYOUT_V2
    return _LAYOUT_V1


__all__ = [
    "detect_layout",
]
