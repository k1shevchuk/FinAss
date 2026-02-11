from dataclasses import dataclass

from app.bot.middlewares.authz import AuthzGuard
from app.domain.services.audit_service import AuditService
from app.domain.services.category_service import CategoryService
from app.domain.services.expense_service import ExpenseService
from app.domain.services.family_service import FamilyService
from app.domain.services.idempotency_service import IdempotencyService
from app.domain.services.onboarding_service import OnboardingService
from app.domain.services.receipt_service import ReceiptService
from app.domain.services.report_service import ReportService
from app.domain.services.settings_service import SettingsService


@dataclass(slots=True)
class AppServices:
    onboarding: OnboardingService
    expense: ExpenseService
    receipt: ReceiptService
    report: ReportService
    family: FamilyService
    categories: CategoryService
    settings: SettingsService
    audit: AuditService
    idempotency: IdempotencyService
    authz_guard: AuthzGuard
