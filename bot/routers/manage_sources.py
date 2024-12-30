# routers/manage_sources.py
import math
import re

from aiogram.utils.keyboard import InlineKeyboardBuilder
from bson.objectid import ObjectId
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

from aiogram.filters.callback_data import CallbackData

from config import ALLOWED_USERS, logger
from database import sources_collection
from states import AddSourceStates

manage_sources_router = Router()

# Сколько источников показывать на одной странице
PER_PAGE = 5


# ------------------ CALLBACK DATA ------------------

class SourcePaginationCallback(CallbackData, prefix="src_pag"):
    """
    Колбэк для переключения страниц.
    """
    action: str  # "page"
    page: int  # номер страницы (1..N)


class SourceActionCallback(CallbackData, prefix="src_act"):
    """
    Колбэк для действий над конкретным источником (активировать / деактивировать / удалить).
    """
    action: str  # "activate", "deactivate", "delete"
    source_id: str  # ObjectId источника в виде строки
    page: int  # Чтобы после действия мы остались на той же странице


# ------------------ ЛОГИКА РЕНДЕРИНГА ------------------


def build_sources_page_text(sources: list, page: int, per_page: int = 5) -> str:
    """
    Собираем текст для верхней части сообщения (список источников на текущей странице).
    """
    total_pages = max(1, math.ceil(len(sources) / per_page))  # хотя бы 1 стр.
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    start_index = (page - 1) * per_page
    end_index = start_index + per_page

    page_slice = sources[start_index:end_index]

    lines = []
    lines.append(f"**Страница** {page}/{total_pages}\n")

    # Перечислим источники на текущей странице
    for i, src in enumerate(page_slice, start=1):
        name = src.get("name", "Без названия")
        url = src.get("url", "—")
        is_active = src.get("active", True)
        status = "✅" if is_active else "🛑"
        lines.append(f"{i}. {name} {status} ({url})")

    # Если совсем нет источников на странице (может быть при удалении)
    if not page_slice:
        lines.append("На этой странице пока нет источников.")

    return "\n".join(lines)


def build_sources_page_keyboard(sources: list, page: int, per_page: int = PER_PAGE) -> InlineKeyboardMarkup:
    """
    Формирует InlineKeyboardMarkup для заданной страницы.

    :param sources: полный список источников (list)
    :param page: номер страницы (1..)
    :param per_page: сколько показываем за одну страницу
    :return: InlineKeyboardMarkup
    """

    builder = InlineKeyboardBuilder()

    # Подсчитаем общее количество страниц
    total_pages = math.ceil(len(sources) / per_page) if sources else 1

    if total_pages < 1:
        total_pages = 1

    # Чтобы не выходить за рамки
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    # Получим нужный срез
    start_index = (page - 1) * per_page
    end_index = start_index + per_page
    page_sources = sources[start_index:end_index]

    # Формируем кнопки
    for src in page_sources:
        source_id = str(src["_id"])
        source_url = src["url"]
        source_name = src["name"]
        is_active = src.get("active", True)

        status_icon = "✅" if is_active else "🛑"
        status_action = "deactivate" if is_active else "activate"

        # Кнопка «Название» — просто для отображения, пусть callback_data="pass" (необязательно)
        btn_name = InlineKeyboardButton(
            text=f"{source_name}",
            callback_data="pass"
        )
        # Кнопка «Активировать / Деактивировать»
        btn_toggle = InlineKeyboardButton(
            text=status_icon,
            callback_data=SourceActionCallback(
                action=status_action,
                source_id=source_id,
                page=page
            ).pack()
        )
        # Кнопка «Удалить»
        btn_delete = InlineKeyboardButton(
            text="🗑",
            callback_data=SourceActionCallback(
                action="delete",
                source_id=source_id,
                page=page
            ).pack()
        )

        builder.row(btn_name, btn_toggle, btn_delete)

    # Добавляем внизу кнопки «Назад» и «Вперёд» (если страниц > 1)
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="← Назад",
                callback_data=SourcePaginationCallback(
                    action="page",
                    page=page - 1
                ).pack()
            )
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(
                text="Вперёд →",
                callback_data=SourcePaginationCallback(
                    action="page",
                    page=page + 1
                ).pack()
            )
        )

    # Можно добавить «N / M» как текст (без callback_data)
    if total_pages > 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text=f"{page}/{total_pages}",
                callback_data="pass"
            )
        )

    if nav_buttons:
        builder.row(*nav_buttons)

    kb = builder.as_markup()

    return kb


# ------------------ ОБРАБОТЧИК КОМАНДЫ ------------------
@manage_sources_router.message(AddSourceStates.waiting_for_sources)
async def process_sources(message: Message, state: FSMContext):
    sources_text = message.text
    lines = sources_text.strip().split('\n')
    added_sources = []
    failed_sources = []

    pattern = re.compile(r'^(?P<link>\S+)\s*\(\s*(?P<name>.+?)\s*\)$')

    for line in lines:
        line = line.strip()
        match = pattern.match(line)
        if match:
            link = match.group('link').strip()
            name = match.group('name').strip()
            if not re.match(r'^https?://', link):
                failed_sources.append(f"{line} (некорректная ссылка)")
                continue

            existing_source = sources_collection.find_one({'url': link})
            if existing_source:
                failed_sources.append(f"{link} ({name}) - уже существует")
                continue

            sources_collection.insert_one({"url": link, "name": name, "active": True})
            added_sources.append(f"{link} ({name})")
        else:
            failed_sources.append(f"{line} (неверный формат)")

    response_messages = []
    if added_sources:
        response_messages.append("Добавлены и активированы:")
        response_messages.extend(added_sources)
    if failed_sources:
        response_messages.append("Не удалось распознать:")
        response_messages.extend(failed_sources)

    await message.answer('\n'.join(response_messages))
    await state.clear()


# ------------------ ОБРАБОТЧИК ПЕРЕКЛЮЧЕНИЯ СТРАНИЦ ------------------

@manage_sources_router.callback_query(SourcePaginationCallback.filter())
async def on_pagination_callback(call: CallbackQuery, callback_data: SourcePaginationCallback):
    """
    Нажали "Назад" или "Вперёд" для перелистывания страниц.
    """
    user_id = call.from_user.id
    if user_id not in ALLOWED_USERS:
        await call.answer("У вас нет прав.", show_alert=True)
        return

    page = callback_data.page

    sources = list(sources_collection.find())
    text = build_sources_page_text(sources, page=page, per_page=PER_PAGE)
    kb = build_sources_page_keyboard(sources, page=page, per_page=PER_PAGE)

    # Обновляем именно text + reply_markup
    try:
        await call.message.edit_text(
            text=text,
            reply_markup=kb,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Ошибка при редактировании страницы: {e}")

    await call.answer()  # убираем "часики"


# ------------------ ОБРАБОТЧИК ДЕЙСТВИЙ НАД ИСТОЧНИКАМИ ------------------

@manage_sources_router.callback_query(SourceActionCallback.filter())
@manage_sources_router.callback_query(SourceActionCallback.filter())
async def on_source_action_callback(call: CallbackQuery, callback_data: SourceActionCallback):
    """
    Нажали на «активировать», «деактивировать» или «удалить».
    """
    user_id = call.from_user.id
    if user_id not in ALLOWED_USERS:
        await call.answer("У вас нет прав.", show_alert=True)
        return

    action = callback_data.action
    source_id = callback_data.source_id
    page = callback_data.page

    source = sources_collection.find_one({"_id": ObjectId(source_id)})
    if not source:
        await call.answer("Источник не найден.", show_alert=True)
        return

    name = source.get("name", "?")
    is_active = source.get("active", True)

    if action == "activate":
        sources_collection.update_one({"_id": ObjectId(source_id)}, {"$set": {"active": True}})
        await call.answer(f"Источник {name} активирован.", show_alert=True)
    elif action == "deactivate":
        sources_collection.update_one({"_id": ObjectId(source_id)}, {"$set": {"active": False}})
        await call.answer(f"Источник {name} деактивирован.", show_alert=True)
    elif action == "delete":
        sources_collection.delete_one({"_id": ObjectId(source_id)})
        await call.answer(f"Источник {name} удалён.", show_alert=True)
    else:
        await call.answer("Неизвестное действие", show_alert=True)
        return

    # Снова формируем список/клаву для того же page
    sources = list(sources_collection.find())

    # Если после удаления вдруг текущая страница стала больше, чем доступно, уменьшаем page
    total_pages = max(1, math.ceil(len(sources) / PER_PAGE))
    if page > total_pages:
        page = total_pages

    text = build_sources_page_text(sources, page=page, per_page=PER_PAGE)
    kb = build_sources_page_keyboard(sources, page=page, per_page=PER_PAGE)

    try:
        await call.message.edit_text(
            text=text,
            reply_markup=kb,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Ошибка при редактировании после действия: {e}")
