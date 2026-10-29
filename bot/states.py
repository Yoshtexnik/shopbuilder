from aiogram.fsm.state import State, StatesGroup


class Checkout(StatesGroup):
    delivery_type = State()
    location = State()
    address = State()
    phone = State()
    payment = State()
    confirm = State()
