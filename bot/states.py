# states.py

from aiogram.fsm.state import State, StatesGroup


# Для примера все состояния собраны здесь

class SetNewsPerHourState(StatesGroup):
    waiting_for_number = State()


class AddSourceStates(StatesGroup):
    waiting_for_sources = State()


class AddKeywordsStates(StatesGroup):
    waiting_for_keywords = State()


class AddBanStates(StatesGroup):
    waiting_for_bans = State()


class SetPublishIntervalState(StatesGroup):
    waiting_for_interval = State()


class SetMaxNewsLengthState(StatesGroup):
    waiting_for_length = State()
