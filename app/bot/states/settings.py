from aiogram.fsm.state import State, StatesGroup


class SettingsStates(StatesGroup):
    waiting_currency = State()
    waiting_timezone = State()
