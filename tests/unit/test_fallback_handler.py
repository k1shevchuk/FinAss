import pytest

from app.bot.handlers.fallback import fallback_message
from app.bot.keyboards.menu import BTN_ADD, BTN_ONB_ATTACH


class _DummyUser:
    def __init__(self, telegram_id: int) -> None:
        self.id = telegram_id


class _DummyMessage:
    def __init__(self, user_id: int | None) -> None:
        self.from_user = _DummyUser(user_id) if user_id is not None else None
        self.sent: list[tuple[str, object]] = []

    async def answer(self, text: str, reply_markup: object | None = None) -> None:
        self.sent.append((text, reply_markup))


class _DummyFamilyService:
    def __init__(self, has_family: bool) -> None:
        self._has_family = has_family

    async def get_actor_family(self, actor_id: int):  # type: ignore[no-untyped-def]
        _ = actor_id
        if not self._has_family:
            return None
        return ("family", "sheet", 1, "Europe/Moscow", "RUB")


class _DummyServices:
    def __init__(self, has_family: bool) -> None:
        self.family = _DummyFamilyService(has_family=has_family)


@pytest.mark.asyncio
async def test_fallback_message_for_onboarding_user() -> None:
    message = _DummyMessage(user_id=10)
    services = _DummyServices(has_family=False)
    await fallback_message(message, services)  # type: ignore[arg-type]
    assert len(message.sent) == 1
    text, markup = message.sent[0]
    assert "Не понял" in text
    assert markup is not None
    keyboard = getattr(markup, "keyboard", [])
    assert any(button.text == BTN_ONB_ATTACH for row in keyboard for button in row)


@pytest.mark.asyncio
async def test_fallback_message_for_connected_user() -> None:
    message = _DummyMessage(user_id=10)
    services = _DummyServices(has_family=True)
    await fallback_message(message, services)  # type: ignore[arg-type]
    assert len(message.sent) == 1
    text, markup = message.sent[0]
    assert "Не понял" in text
    assert markup is not None
    keyboard = getattr(markup, "keyboard", [])
    assert any(button.text == BTN_ADD for row in keyboard for button in row)
