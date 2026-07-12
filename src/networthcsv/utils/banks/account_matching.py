"""Mail/statement matching models and merge facade."""

from __future__ import annotations

from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from networthcsv.utils.banks._matching_validators import (
    AccountTypeName,
    BodyContains,
    FromAddresses,
    OptionalAccountTypeName,
    OptionalBodyContains,
    OptionalFromAddresses,
    OptionalSubjects,
    OptionalTextContains,
    OptionalTextNotContains,
    Subjects,
    TextContains,
    TextNotContains,
)

__all__ = [
    "AccountMatching",
    "MailMatchConfig",
    "MailMatchOverride",
    "MatchingFields",
    "MatchingFieldsCore",
    "StatementCleanupConfig",
    "StatementCleanupOverride",
]


class MatchingFieldsCore(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", populate_by_name=True
    )


class MailMatchConfig(MatchingFieldsCore):
    subjects: Subjects
    body_contains: BodyContains = []
    from_addresses: FromAddresses = Field(default_factory=list, alias="from")


class MailMatchOverride(MatchingFieldsCore):
    subjects: OptionalSubjects = None
    body_contains: OptionalBodyContains = None
    from_addresses: OptionalFromAddresses = Field(default=None, alias="from")


class StatementCleanupConfig(MatchingFieldsCore):
    text_contains: TextContains = []
    text_not_contains: TextNotContains = []


class StatementCleanupOverride(MatchingFieldsCore):
    text_contains: OptionalTextContains = None
    text_not_contains: OptionalTextNotContains = None


class MatchingFields(MatchingFieldsCore):
    account_type: AccountTypeName = Field(default="credit_card", alias="type")
    mail: MailMatchConfig
    statement: StatementCleanupConfig = Field(default_factory=StatementCleanupConfig)


class _MatchingOverlay(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    account_type: OptionalAccountTypeName = Field(default=None, alias="type")
    mail: MailMatchOverride | None = None
    statement: StatementCleanupOverride | None = None


class AccountMatching:
    """Merge bank matching defaults with user/account overlays."""

    @staticmethod
    def _merge_model_fields(
        base: BaseModel, overlay: BaseModel | None
    ) -> dict[str, object]:
        merged = cast(dict[str, object], base.model_dump(by_alias=True))
        if overlay is None:
            return merged
        overlay_dump = cast(
            dict[str, object], overlay.model_dump(exclude_none=True, by_alias=True)
        )
        merged.update(overlay_dump)
        return merged

    @staticmethod
    def _merge_mail(
        base: MailMatchConfig, overlay: MailMatchOverride | None
    ) -> MailMatchConfig:
        if overlay is None:
            return base
        return MailMatchConfig.model_validate(
            AccountMatching._merge_model_fields(base, overlay)
        )

    @staticmethod
    def _merge_statement(
        base: StatementCleanupConfig, overlay: StatementCleanupOverride | None
    ) -> StatementCleanupConfig:
        if overlay is None:
            return base
        return StatementCleanupConfig.model_validate(
            AccountMatching._merge_model_fields(base, overlay)
        )

    @staticmethod
    def _overlay_from(model: BaseModel) -> _MatchingOverlay:
        dumped = cast(
            dict[str, object], model.model_dump(exclude_none=True, by_alias=True)
        )
        overlay_data = {
            key: dumped[key] for key in ("type", "mail", "statement") if key in dumped
        }
        return _MatchingOverlay.model_validate(overlay_data)

    @staticmethod
    def merge(base: MatchingFields, *overlays: BaseModel) -> MatchingFields:
        mail = base.mail
        statement = base.statement
        account_type = base.account_type
        for overlay in overlays:
            parsed = AccountMatching._overlay_from(overlay)
            if parsed.account_type is not None:
                account_type = parsed.account_type
            mail = AccountMatching._merge_mail(mail, parsed.mail)
            statement = AccountMatching._merge_statement(statement, parsed.statement)
        return MatchingFields.model_validate(
            {
                "type": account_type,
                "mail": mail.model_dump(by_alias=True),
                "statement": statement.model_dump(by_alias=True),
            }
        )
