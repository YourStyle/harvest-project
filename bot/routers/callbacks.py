# routers/callbacks.py

from aiogram.filters.callback_data import CallbackData


class SourceCallback(CallbackData, prefix="source"):
    action: str
    source_id: str


class KeywordCallback(CallbackData, prefix="keyword"):
    action: str
    keyword_id: str


class BanCallback(CallbackData, prefix="ban"):
    action: str
    ban_id: str
