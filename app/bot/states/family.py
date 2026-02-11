from aiogram.fsm.state import State, StatesGroup


class FamilyStates(StatesGroup):
    waiting_invite_target = State()
    waiting_remove_member_id = State()
    waiting_join_code = State()
