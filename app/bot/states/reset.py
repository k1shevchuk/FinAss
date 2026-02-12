from aiogram.fsm.state import State, StatesGroup


class ResetStates(StatesGroup):
    waiting_confirmation = State()
