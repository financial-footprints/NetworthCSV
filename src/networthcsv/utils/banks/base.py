"""Abstract base classes and default credit-card handler."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal

from networthcsv.settings import (
    MailMatchConfig,
    MatchingFields,
    StatementCleanupConfig,
)
from networthcsv.utils.banks.helpers.amounts import DEFAULT_BALANCE_MATCH_TOLERANCE
from networthcsv.utils.banks.helpers.text import (
    purge_drop_sections,
    sanitize_statement_text,
    trim_by_markers,
)


class BankHandler(ABC):
    @abstractmethod
    def mail_subjects(self) -> list[str]: ...

    @abstractmethod
    def clean_text(self, raw: str) -> str: ...

    @abstractmethod
    def get_statement_date(self, text: str) -> date | None: ...

    @abstractmethod
    def get_statement_period(self, text: str) -> tuple[date | None, date | None]: ...

    @abstractmethod
    def get_opening_balance(self, text: str) -> str | None: ...

    @abstractmethod
    def get_closing_balance(self, text: str) -> str | None: ...

    def mail_body_contains(self) -> list[str]:
        return []

    def mail_from_addresses(self) -> list[str]:
        return []

    def account_type(self) -> str:
        return "credit_card"

    def balance_match_tolerance(self) -> Decimal:
        return DEFAULT_BALANCE_MATCH_TOLERANCE

    def period_start_day(self) -> int | None:
        return None

    def matching_defaults(self) -> MatchingFields:
        return MatchingFields.model_validate(
            {
                "type": self.account_type(),
                "mail": MailMatchConfig.model_validate(
                    {
                        "subjects": self.mail_subjects(),
                        "body_contains": self.mail_body_contains(),
                        "from": self.mail_from_addresses(),
                    }
                ).model_dump(by_alias=True),
                "statement": StatementCleanupConfig().model_dump(),
            }
        )


class CreditCardHandler(BankHandler):
    def trim_start(self) -> list[str]:
        return []

    def trim_end(self) -> list[str]:
        return []

    def drop_sections(self) -> list[str]:
        return []

    def clean_text(self, raw: str) -> str:
        trimmed = trim_by_markers(
            raw,
            trim_start=self.trim_start(),
            trim_end=self.trim_end(),
        )
        sanitized = sanitize_statement_text(trimmed)
        return purge_drop_sections(sanitized, drop_sections=self.drop_sections())

    def get_statement_period(self, text: str) -> tuple[date | None, date | None]:
        end = self.get_statement_date(text)
        if end is not None:
            return None, end
        return None, None
