from aiogram.filters.callback_data import CallbackData


class MenuCB(CallbackData, prefix="menu"):
    act: str


class CatCB(CallbackData, prefix="cat"):
    id: int


class ProdCB(CallbackData, prefix="prd"):
    id: int


class QtyCB(CallbackData, prefix="qty"):
    id: int
    q: int


class AddCB(CallbackData, prefix="add"):
    id: int
    q: int


class CartCB(CallbackData, prefix="cart"):
    act: str
    id: int = 0


class CheckoutCB(CallbackData, prefix="co"):
    act: str
    val: str = ""


class StatusCB(CallbackData, prefix="ost"):
    id: int
    st: str


class MyOrderCB(CallbackData, prefix="mo"):
    id: int
    act: str
