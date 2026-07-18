"""IDFC bank handlers."""

from networthcsv.utils.banks.idfc import default, wow
from networthcsv.utils.banks.idfc.wow import handler  # noqa: F401

__all__ = ["default", "handler", "wow"]
