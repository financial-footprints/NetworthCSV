"""IDFC WOW PDF layout detection and version handlers."""

from __future__ import annotations

from typing import Literal

from networthcsv.utils.banks.idfc.summary import (
    _header_block_window,
    _idfc_classic_summary_amounts,
    _parse_header_block_data,
    normalize_cr_dr_layout,
)
from networthcsv.utils.banks.idfc.wow.common import has_inline_summary_header
from networthcsv.utils.banks.idfc.wow.version1 import LayoutV1
from networthcsv.utils.banks.idfc.wow.version2 import LayoutV2
from networthcsv.utils.banks.idfc.wow.version3 import LayoutV3

LayoutVersion = Literal["v1", "v2", "v3"]

_LAYOUT_V1 = LayoutV1()
_LAYOUT_V2 = LayoutV2()
_LAYOUT_V3 = LayoutV3()


def _has_classic_layout(text: str) -> bool:
    if _idfc_classic_summary_amounts(text) is not None:
        return True
    window = normalize_cr_dr_layout(_header_block_window(text))
    return _parse_header_block_data(window) is not None


def detect_layout(text: str) -> LayoutVersion:
    """Pick PDF layout version from raw or sanitized statement text."""
    normalized = normalize_cr_dr_layout(text)
    if has_inline_summary_header(normalized):
        return "v2"
    if _has_classic_layout(normalized):
        return "v1"
    return "v3"


def get_layout(text: str) -> LayoutV1 | LayoutV2 | LayoutV3:
    layout_id = detect_layout(text)
    if layout_id == "v2":
        return _LAYOUT_V2
    if layout_id == "v1":
        return _LAYOUT_V1
    return _LAYOUT_V3


__all__ = [
    "LayoutV1",
    "LayoutV2",
    "LayoutV3",
    "LayoutVersion",
    "detect_layout",
    "get_layout",
]
