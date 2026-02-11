from dataclasses import dataclass, field

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domain.entities import OwnerContext, SpreadsheetInfo
from app.infra.db.models import Base


class FakeSheetsGateway:
    async def create_spreadsheet(self, owner: OwnerContext) -> SpreadsheetInfo:
        return SpreadsheetInfo(
            sheet_id=f"sheet-{owner.telegram_id}",
            sheet_url=f"https://docs.google.com/spreadsheets/d/sheet-{owner.telegram_id}",
        )

    async def attach_existing_spreadsheet(
        self,
        *,
        sheet_id: str,
        owner: OwnerContext,
    ) -> SpreadsheetInfo:
        _ = owner
        return SpreadsheetInfo(
            sheet_id=sheet_id,
            sheet_url=f"https://docs.google.com/spreadsheets/d/{sheet_id}",
        )


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple]] = []

    async def enqueue_job(self, name: str, *args):
        self.jobs.append((name, args))
        return "job-id"


@dataclass
class StubSecret:
    value: str

    def get_secret_value(self) -> str:
        return self.value


@dataclass
class StubSettings:
    default_timezone: str = "Europe/Berlin"
    default_currency: str = "RUB"
    default_rounding_mode: str = "HALF_UP"
    invite_ttl_seconds: int = 3600
    webhook_secret_token: StubSecret | None = field(default_factory=lambda: StubSecret("pepper"))


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()
