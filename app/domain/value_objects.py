from enum import StrEnum


class MembershipRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"


class ExpenseSource(StrEnum):
    MANUAL = "manual"
    RECEIPT = "receipt"


class ReportPeriodKind(StrEnum):
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
    CUSTOM = "custom"
