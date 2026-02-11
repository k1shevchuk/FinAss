from aiogram.fsm.state import State, StatesGroup


class CategoryStates(StatesGroup):
    waiting_add_payload = State()
    waiting_enable_name = State()
    waiting_disable_name = State()
