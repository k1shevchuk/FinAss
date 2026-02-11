from aiogram.fsm.state import State, StatesGroup


class AddExpenseStates(StatesGroup):
    choose_mode = State()
    waiting_item_name = State()
    waiting_quantity = State()
    waiting_unit_price = State()
    waiting_category = State()
    confirm = State()
    waiting_continue_action = State()
