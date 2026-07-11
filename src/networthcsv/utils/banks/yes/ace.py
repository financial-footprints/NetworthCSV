"""YES ACE credit card handler."""

from __future__ import annotations

from networthcsv.utils.banks import register
from networthcsv.utils.banks.yes.default import YesDefaultHandler


@register("yes", "ace")
class YesAceHandler(YesDefaultHandler):
    def mail_subjects(self) -> list[str]:
        return ["Your YES_BANK_ACE Rupay Credit Card E-Statement"]
