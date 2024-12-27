# routers/commands.py

import re
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from config import ALLOWED_USERS, logger
from database import config_collection, stats_collection
from states import (
    SetNewsPerHourState,
    SetPublishIntervalState,
    SetMaxNewsLengthState
)

commands_router = Router()


@commands_router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Бот запущен и будет публиковать новости в заданном режиме.")


@commands_router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    stats = stats_collection.find({"timestamp": {"$gte": one_hour_ago}})

    total_sent = sum(stat['sent_count'] for stat in stats)

    await message.answer(f"За последний час было отправлено {total_sent} новостей.")


# ----------- Пример установки параметров через FSM ------------

@commands_router.message(Command("set_news_per_interval"))
async def set_news_per_hour_command(message: Message, state: FSMContext):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    await message.answer("Пожалуйста, введите количество новостей за интервал:")
    await state.set_state(SetNewsPerHourState.waiting_for_number)


@commands_router.message(SetNewsPerHourState.waiting_for_number)
async def process_news_per_hour(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите корректное число.")
        return

    news_per_hour = int(message.text)
    config_collection.update_one(
        {"_id": "bot_config"},
        {"$set": {"news_per_hour": news_per_hour}},
        upsert=True
    )
    await message.answer(f"Количество новостей за интервал установлено на {news_per_hour}.")
    await state.clear()


@commands_router.message(Command("set_publish_interval"))
async def set_publish_interval_command(message: Message, state: FSMContext):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    await message.answer("Пожалуйста, введите интервал публикации в секундах:")
    await state.set_state(SetPublishIntervalState.waiting_for_interval)


@commands_router.message(SetPublishIntervalState.waiting_for_interval)
async def process_publish_interval(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите корректное число (интервал в секундах).")
        return

    publish_interval = int(message.text)
    if publish_interval <= 0:
        await message.answer("Интервал публикации должен быть больше нуля.")
        return

    config_collection.update_one(
        {"_id": "bot_config"},
        {"$set": {"publish_interval": publish_interval}},
        upsert=True
    )
    await message.answer(f"Интервал публикации установлен на {publish_interval} секунд.")
    await state.clear()


@commands_router.message(Command("set_max_news_length"))
async def set_max_news_length_command(message: Message, state: FSMContext):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    await message.answer("Пожалуйста, введите максимальную длину текста новости (в символах):")
    await state.set_state(SetMaxNewsLengthState.waiting_for_length)


@commands_router.message(SetMaxNewsLengthState.waiting_for_length)
async def process_max_news_length(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите корректное число.")
        return

    max_news_length = int(message.text)
    if max_news_length <= 0 or max_news_length > 4096:
        await message.answer("Длина новости должна быть больше 0 и ≤ 4096 символов.")
        return

    config_collection.update_one(
        {"_id": "bot_config"},
        {"$set": {"max_news_length": max_news_length}},
        upsert=True
    )
    await message.answer(f"Максимальная длина текста новости установлена на {max_news_length} символов.")
    await state.clear()
