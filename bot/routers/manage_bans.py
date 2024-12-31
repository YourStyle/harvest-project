# routers/manage_bans.py
import math

from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder
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

PER_PAGE = 5


# ---------- CALLBACKS ----------

class BanPaginationCallback(CallbackData, prefix="ban_pag"):
    action: str  # "page"
    page: int


class BanActionCallback(CallbackData, prefix="ban_act"):
    action: str  # "delete"
    ban_id: str
    page: int


# ---------- ФУНКЦИИ РЕНДЕРА ----------

def build_bans_page_text(bans: list, page: int, per_page: int = PER_PAGE) -> str:
    total_pages = max(1, math.ceil(len(bans) / per_page))
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    start_i = (page - 1) * per_page
    end_i = start_i + per_page
    page_slice = bans[start_i:end_i]

    lines = []
    lines.append(f"<b>Страница</b> {page}/{total_pages}\n")

    if not page_slice:
        lines.append("На этой странице пока нет исключений (бан-слов).")
    else:
        for i, ban in enumerate(page_slice, start=1):
            ban_text = ban.get("keyword", "")
            lines.append(f"{i}. {ban_text}")

    return "\n".join(lines)


def build_bans_page_keyboard(bans: list, page: int, per_page: int = PER_PAGE) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    total_pages = max(1, math.ceil(len(bans) / per_page))

    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    start_i = (page - 1) * per_page
    end_i = start_i + per_page
    page_slice = bans[start_i:end_i]

    for ban in page_slice:
        ban_id = str(ban["_id"])
        ban_text = ban.get("keyword", "")

        btn_name = InlineKeyboardButton(text=ban_text, callback_data="pass")
        btn_delete = InlineKeyboardButton(
            text="🗑",
            callback_data=BanActionCallback(action="delete", ban_id=ban_id, page=page).pack()
        )
        builder.row(btn_name, btn_delete)

    # Навигация
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="← Назад",
                callback_data=BanPaginationCallback(action="page", page=page - 1).pack()
            )
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(
                text="Вперёд →",
                callback_data=BanPaginationCallback(action="page", page=page + 1).pack()
            )
        )
    if total_pages > 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text=f"{page}/{total_pages}",
                callback_data="pass"
            )
        )
    if nav_buttons:
        builder.row(*nav_buttons)

    return builder.as_markup()


# ---------- ОБРАБОТЧИК ПЕРЕКЛЮЧЕНИЯ СТРАНИЦ ----------

@manage_bans_router.callback_query(BanPaginationCallback.filter())
async def on_bans_pagination(call: CallbackQuery, callback_data: BanPaginationCallback):
    user_id = call.from_user.id
    if user_id not in ALLOWED_USERS:
        await call.answer("У вас нет прав.", show_alert=True)
        return

    page = callback_data.page
    all_bans = list(bans_collection.find())

    text = build_bans_page_text(all_bans, page=page, per_page=PER_PAGE)
    kb = build_bans_page_keyboard(all_bans, page=page, per_page=PER_PAGE)

    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer()


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


# ---------- ОБРАБОТЧИК УДАЛЕНИЯ ----------

@manage_bans_router.callback_query(BanActionCallback.filter())
async def on_ban_action(call: CallbackQuery, callback_data: BanActionCallback):
    user_id = call.from_user.id
    if user_id not in ALLOWED_USERS:
        await call.answer("У вас нет прав.", show_alert=True)
        return

    if callback_data.action == "delete":
        ban_doc = bans_collection.find_one({"_id": ObjectId(callback_data.ban_id)})
        if ban_doc:
            bans_collection.delete_one({"_id": ObjectId(callback_data.ban_id)})
            await call.answer(f"Исключение '{ban_doc['keyword']}' удалено.", show_alert=True)
        else:
            await call.answer("Исключение не найдено.", show_alert=True)
            return
    else:
        await call.answer("Неизвестное действие", show_alert=True)
        return

    # После удаления пересчитываем страницу
    page = callback_data.page
    all_bans = list(bans_collection.find())
    total_pages = max(1, math.ceil(len(all_bans) / PER_PAGE))
    if page > total_pages:
        page = total_pages

    text = build_bans_page_text(all_bans, page=page, per_page=PER_PAGE)
    kb = build_bans_page_keyboard(all_bans, page=page, per_page=PER_PAGE)

    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
