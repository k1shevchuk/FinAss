from aiogram.fsm.state import State, StatesGroup


class AccountsStates(StatesGroup):
    waiting_topup_amount = State()
    waiting_transfer_amount = State()
    waiting_spend_savings_amount = State()
