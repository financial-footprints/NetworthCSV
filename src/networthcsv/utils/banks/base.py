"""Abstract base classes and default credit-card handler."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from networthcsv.utils.banks.account_matching import (
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

if TYPE_CHECKING:
    from networthcsv.settings import ResolvedAccount
    from networthcsv.utils.banks.period import PeriodSource


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

    def get_statement_reference(self, text: str) -> str | None:
        return None

    def mail_body_contains(self) -> list[str]:
        return []

    def mail_from_addresses(self) -> list[str]:
        return []

    def account_type(self) -> str:
        return "credit_card"

    def balance_match_tolerance(self) -> Decimal:
        return DEFAULT_BALANCE_MATCH_TOLERANCE

    def year_display(self) -> Literal["fiscal_year", "calendar_year"]:
        return "calendar_year"

    def annual_mail_subjects(self) -> list[str]:
        return []

    def annual_mail_body_contains(self) -> list[str]:
        return []

    def is_annual_statement(self, text: str) -> bool:
        return False

    def get_annual_period(self, text: str) -> tuple[date, date] | None:
        return None

    def resolve_csv_period_key_with_source(
        self,
        csv_text: str,
        filename: str,
        *,
        account: ResolvedAccount,
    ) -> tuple[str, PeriodSource]:
        """Resolve period key for a bank CSV statement. Default: unknown."""
        _ = (csv_text, filename, account)
        return "unknown-month", "unknown"

    def resolve_csv_period_bounds(
        self,
        csv_text: str,
        *,
        account: ResolvedAccount,
    ) -> tuple[date | None, date | None]:
        """Return inclusive period bounds from CSV content. Default: none."""
        _ = (csv_text, account)
        return None, None

    def matching_defaults(self) -> MatchingFields:
        subjects = [*self.mail_subjects(), *self.annual_mail_subjects()]
        body_contains = [
            *self.mail_body_contains(),
            *self.annual_mail_body_contains(),
        ]
        return MatchingFields.model_validate(
            {
                "type": self.account_type(),
                "mail": MailMatchConfig.model_validate(
                    {
                        "subjects": subjects,
                        "body_contains": body_contains,
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
