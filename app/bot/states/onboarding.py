from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    waiting_setup_mode = State()
    waiting_sheet_link = State()
    waiting_join_code = State()
    waiting_initial_main_balance = State()
    waiting_initial_savings_balance = State()
