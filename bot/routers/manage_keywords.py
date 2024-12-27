# routers/manage_keywords.py

from bson.objectid import ObjectId
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

from config import ALLOWED_USERS
from database import keywords_collection
from states import AddKeywordsStates
from .callbacks import KeywordCallback

manage_keywords_router = Router()

@manage_keywords_router.message(Command("add_keywords"))
async def add_keywords_command(message: Message, state: FSMContext):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    await message.answer(
        "Пожалуйста, отправьте список ключевых слов, по одному на строку."
    )
    await state.set_state(AddKeywordsStates.waiting_for_keywords)


@manage_keywords_router.message(AddKeywordsStates.waiting_for_keywords)
async def process_keywords(message: Message, state: FSMContext):
    lines = message.text.strip().split('\n')
    added_keywords = []
    failed_keywords = []

    for line in lines:
        line = line.strip()
        existing = keywords_collection.find_one({'keyword': line})
        if existing:
            failed_keywords.append(f"{line} - уже существует")
        else:
            keywords_collection.insert_one({'keyword': line})
            added_keywords.append(line)

    response = []
    if added_keywords:
        response.append("Добавлены ключевые слова:")
        response.extend(added_keywords)
    if failed_keywords:
        response.append("Не добавлены (уже существуют):")
        response.extend(failed_keywords)

    await message.answer("\n".join(response))
    await state.clear()


@manage_keywords_router.message(Command("manage_keywords"))
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


@manage_keywords_router.callback_query(KeywordCallback.filter())
async def process_keyword_callback(callback_query: CallbackQuery, callback_data: KeywordCallback):
    user_id = callback_query.from_user.id
    if user_id not in ALLOWED_USERS:
        await callback_query.answer("У вас нет прав.", show_alert=True)
        return

    if callback_data.action == 'delete':
        keyword = keywords_collection.find_one({'_id': ObjectId(callback_data.keyword_id)})
        if keyword:
            keywords_collection.delete_one({'_id': ObjectId(callback_data.keyword_id)})
            await callback_query.answer(f"Ключевое слово '{keyword['keyword']}' удалено.", show_alert=True)
            await callback_query.message.delete()
        else:
            await callback_query.answer("Ключевое слово не найдено.", show_alert=True)
