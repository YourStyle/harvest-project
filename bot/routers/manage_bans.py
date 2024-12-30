# routers/manage_bans.py

from bson.objectid import ObjectId
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from config import ALLOWED_USERS
from database import bans_collection
from states import AddBanStates
from .callbacks import BanCallback

manage_bans_router = Router()




@manage_bans_router.message(AddBanStates.waiting_for_bans)
async def process_bans(message: Message, state: FSMContext):
    lines = message.text.strip().split('\n')
    added_bans = []
    failed_bans = []

    for line in lines:
        line = line.strip()
        existing = bans_collection.find_one({'keyword': line})
        if existing:
            failed_bans.append(f"{line} - уже существует")
        else:
            bans_collection.insert_one({'keyword': line})
            added_bans.append(line)

    resp = []
    if added_bans:
        resp.append("Добавлены исключения:")
        resp.extend(added_bans)
    if failed_bans:
        resp.append("Не добавлены (уже существуют):")
        resp.extend(failed_bans)

    await message.answer("\n".join(resp))
    await state.clear()


@manage_bans_router.callback_query(BanCallback.filter())
async def process_ban_callback(callback_query: CallbackQuery, callback_data: BanCallback):
    user_id = callback_query.from_user.id
    if user_id not in ALLOWED_USERS:
        await callback_query.answer("У вас нет прав.", show_alert=True)
        return

    ban_doc = bans_collection.find_one({'_id': ObjectId(callback_data.ban_id)})
    if not ban_doc:
        await callback_query.answer("Исключение не найдено.", show_alert=True)
        return

    ban_text = ban_doc['keyword']
    # Удаляем
    bans_collection.delete_one({'_id': ObjectId(callback_data.ban_id)})
    await callback_query.answer(f"Исключение '{ban_text}' удалено.", show_alert=True)
    await callback_query.message.delete()
