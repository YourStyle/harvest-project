# routers/commands.py

import re
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

from config import ALLOWED_USERS, logger
from database import config_collection, stats_collection, sources_collection, keywords_collection, bans_collection
from states import (
    SetNewsPerHourState,
    SetPublishIntervalState,
    SetMaxNewsLengthState,
    AddSourceStates,
    AddKeywordsStates,
    AddBanStates
)
from .callbacks import KeywordCallback, BanCallback

from routers.manage_sources import build_sources_page_keyboard, build_sources_page_text

PER_PAGE = 5

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


# ------------------ ОБРАБОТЧИК ИСТОЧНИКОВ ------------------

@commands_router.message(Command("add_sources"))
async def add_source_command(message: Message, state: FSMContext):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    await message.answer(
        "Пожалуйста, отправьте список источников в формате:\n"
        "ссылка (Название)\n\n"
        "Можно несколько строк подряд."
    )
    await state.set_state(AddSourceStates.waiting_for_sources)


@commands_router.message(Command("manage_sources"))
async def cmd_manage_sources(message: Message):
    """
    При вводе /manage_sources выдаём первое сообщение (1-я страница).
    """
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    sources = list(sources_collection.find())
    page = 1

    text = build_sources_page_text(sources, page=page, per_page=PER_PAGE)
    kb = build_sources_page_keyboard(sources, page=page, per_page=PER_PAGE)

    # Отправляем текст + клавиатуру
    await message.answer(text, reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True)


# ------------------ ОБРАБОТЧИК КЛЮЧЕВЫХ СЛОВ ------------------

@commands_router.message(Command("add_keywords"))
async def add_keywords_command(message: Message, state: FSMContext):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    await message.answer(
        "Пожалуйста, отправьте список ключевых слов, по одному на строку."
    )
    await state.set_state(AddKeywordsStates.waiting_for_keywords)


@commands_router.message(Command("manage_keywords"))
async def manage_keywords(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("У вас нет прав.")
        return

    keywords = list(keywords_collection.find())
    if not keywords:
        await message.answer("Список ключевых слов пуст.")
        return

    for kw in keywords:
        kw_id = str(kw['_id'])
        kw_text = kw['keyword']

        buttons = [[
            InlineKeyboardButton(
                text='🗑',
                callback_data=KeywordCallback(action='delete', keyword_id=kw_id).pack()
            )
        ]]
        await message.answer(
            kw_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )


# ------------------ ОБРАБОТЧИК ИСКЛЮЧЕНИЙ ------------------

@commands_router.message(Command("add_banwords"))
async def add_banwords_command(message: Message, state: FSMContext):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("У вас нет прав.")
        return

    await message.answer(
        "Пожалуйста, отправьте список исключений (бан-слов), по одному на строку."
    )
    await state.set_state(AddBanStates.waiting_for_bans)


@commands_router.message(Command("manage_bans"))
async def manage_bans(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("У вас нет прав.")
        return

    bans = list(bans_collection.find())
    if not bans:
        await message.answer("Список исключений пуст.")
        return

    for ban in bans:
        ban_id = str(ban['_id'])
        ban_text = ban['keyword']

        buttons = [[
            InlineKeyboardButton(
                text='🗑',
                callback_data=BanCallback(action='delete', ban_id=ban_id).pack()
            )
        ]]
        await message.answer(
            ban_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
