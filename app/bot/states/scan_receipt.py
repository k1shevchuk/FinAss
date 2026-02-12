from aiogram.fsm.state import State, StatesGroup


class ScanReceiptStates(StatesGroup):
    waiting_photo = State()
    waiting_fallback_choice = State()
    waiting_fallback_total = State()
    waiting_fallback_category = State()
    waiting_fallback_item_name = State()
    confirm_items = State()
    confirm_fallback = State()
