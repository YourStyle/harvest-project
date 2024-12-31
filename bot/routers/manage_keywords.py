# routers/manage_keywords.py
import math

from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder
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


PER_PAGE = 5  # сколько ключевых слов на одной странице


# ---------- CALLBACKS ----------

class KeywordPaginationCallback(CallbackData, prefix="kw_pag"):
    action: str  # "page"
    page: int    # Номер страницы

class KeywordActionCallback(CallbackData, prefix="kw_act"):
    action: str       # Пока только "delete"
    keyword_id: str   # ObjectId
    page: int         # На какой странице сейчас находимся


# ---------- ФУНКЦИИ РЕНДЕРА ТЕКСТА И КЛАВИАТУРЫ ----------

def build_keywords_page_text(keywords: list, page: int, per_page: int = PER_PAGE) -> str:
    """
    Генерируем текст для верха сообщения (список ключевых слов).
    """
    total_pages = max(1, math.ceil(len(keywords) / per_page))
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    start_i = (page - 1) * per_page
    end_i = start_i + per_page
    page_slice = keywords[start_i:end_i]

    lines = []
    lines.append(f"<b>Страница</b> {page}/{total_pages}\n")

    if not page_slice:
        lines.append("На этой странице пока нет ключевых слов.")
    else:
        for i, kw in enumerate(page_slice, start=1):
            kw_text = kw.get("keyword", "")
            lines.append(f"{i}. {kw_text}")

    return "\n".join(lines)


def build_keywords_page_keyboard(keywords: list, page: int, per_page: int = PER_PAGE) -> InlineKeyboardMarkup:
    """
    Формируем InlineKeyboardMarkup для заданной страницы.
    """
    builder = InlineKeyboardBuilder()

    total_pages = max(1, math.ceil(len(keywords) / per_page))
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    start_i = (page - 1) * per_page
    end_i = start_i + per_page
    page_slice = keywords[start_i:end_i]

    # На каждой строке: ТЕКСТ ключевого слова и кнопка "удалить"
    for kw in page_slice:
        kw_id = str(kw["_id"])
        kw_text = kw.get("keyword", "")

        # Кнопка "Название" (просто pass), если нужно
        btn_name = InlineKeyboardButton(text=kw_text, callback_data="pass")
        # Кнопка "Удалить"
        btn_del = InlineKeyboardButton(
            text="🗑",
            callback_data=KeywordActionCallback(
                action="delete",
                keyword_id=kw_id,
                page=page
            ).pack()
        )
        builder.row(btn_name, btn_del)

    # Кнопки "Назад" / "Вперёд"
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="← Назад",
                callback_data=KeywordPaginationCallback(action="page", page=page-1).pack()
            )
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(
                text="Вперёд →",
                callback_data=KeywordPaginationCallback(action="page", page=page+1).pack()
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


# ---------- ОБРАБОТЧИК ПАГИНАЦИИ (Назад/Вперёд) ----------

@manage_keywords_router.callback_query(KeywordPaginationCallback.filter())
async def on_keywords_pagination(call: CallbackQuery, callback_data: KeywordPaginationCallback):
    user_id = call.from_user.id
    if user_id not in ALLOWED_USERS:
        await call.answer("У вас нет прав.", show_alert=True)
        return

    page = callback_data.page
    all_keywords = list(keywords_collection.find())

    text = build_keywords_page_text(all_keywords, page=page, per_page=PER_PAGE)
    kb = build_keywords_page_keyboard(all_keywords, page=page, per_page=PER_PAGE)

    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer()


# ---------- ОБРАБОТЧИК ДЕЙСТВИЙ (УДАЛИТЬ) ----------

@manage_keywords_router.callback_query(KeywordActionCallback.filter())
async def on_keyword_action(call: CallbackQuery, callback_data: KeywordActionCallback):
    user_id = call.from_user.id
    if user_id not in ALLOWED_USERS:
        await call.answer("У вас нет прав.", show_alert=True)
        return

    if callback_data.action == "delete":
        keyword_doc = keywords_collection.find_one({"_id": ObjectId(callback_data.keyword_id)})
        if keyword_doc:
            keywords_collection.delete_one({"_id": ObjectId(callback_data.keyword_id)})
            await call.answer(f"Ключевое слово '{keyword_doc['keyword']}' удалено.", show_alert=True)
        else:
            await call.answer("Ключевое слово не найдено.", show_alert=True)
            return
    else:
        await call.answer("Неизвестное действие.", show_alert=True)
        return

    # Обновляем текущую страницу (на случай, если удалили последний элемент)
    page = callback_data.page
    all_keywords = list(keywords_collection.find())
    total_pages = max(1, math.ceil(len(all_keywords) / PER_PAGE))
    if page > total_pages:
        page = total_pages

    text = build_keywords_page_text(all_keywords, page=page, per_page=PER_PAGE)
    kb = build_keywords_page_keyboard(all_keywords, page=page, per_page=PER_PAGE)

    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

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