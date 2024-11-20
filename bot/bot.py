import asyncio
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from aiogram.filters.callback_data import CallbackData
from bson.objectid import ObjectId

import pymongo
from pymongo.errors import PyMongoError
from aiogram.utils.markdown import text, bold, hlink
import logging


BOT_TOKEN="7728371504:AAE9OKYCW5MVBYPB-nNJn60BZTk3viOxlzA"
CHANNEL_ID="-1002370678576"
MONGODB_URI="mongodb://Admin:PasswordForMongo63@194.87.186.63/admin?authMechanism=SCRAM-SHA-256"
DATABASE_NAME="news_db"
COLLECTION_NAME="articles"

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация MongoDB клиента
mongo_client = pymongo.MongoClient("194.87.186.63", username='Admin', password='PasswordForMongo63',
                                   authSource='admin', authMechanism='SCRAM-SHA-256')
db = mongo_client[DATABASE_NAME]
collection = db[COLLECTION_NAME]
sources_collection = db['sources']
config_collection = db['config']

stats_collection = db['statistics']

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Максимальная длина сообщения Telegram
MAX_MESSAGE_LENGTH = 4096

default_config = {
    "_id": "bot_config",
    "news_per_hour": 5  # Значение по умолчанию
}

config_collection.update_one(
    {"_id": "bot_config"},
    {"$setOnInsert": default_config},
    upsert=True
)


# Определение класса состояний для FSM
class SetNewsPerHourState(StatesGroup):
    waiting_for_number = State()


# Обработчик команды /set_news_per_hour
@dp.message(Command("set_news_per_hour"))
async def set_news_per_hour_command(message: Message, state: FSMContext):
    if message.from_user.id not in ALLOWED_USERS:
        await message.reply("У вас нет прав для выполнения этой команды.")
        return

    await message.reply("Пожалуйста, введите количество новостей в час:")
    await state.set_state(SetNewsPerHourState.waiting_for_number)


# Обработчик ввода количества новостей в час
@dp.message(SetNewsPerHourState.waiting_for_number)
async def process_news_per_hour(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.reply("Пожалуйста, введите корректное число.")
        return

    news_per_hour = int(message.text)
    config_collection.update_one(
        {"_id": "bot_config"},
        {"$set": {"news_per_hour": news_per_hour}},
        upsert=True
    )
    await message.reply(f"Количество новостей в час установлено на {news_per_hour}.")
    await state.clear()


def split_text(text, max_length=MAX_MESSAGE_LENGTH):
    """
    Разбивает текст на части, каждая из которых не превышает max_length символов.
    Постарается разбивать по переносам строк для сохранения читаемости.
    """
    if len(text) <= max_length:
        return [text]

    parts = []
    while len(text) > max_length:
        # Найти последнее вхождение переноса строки в пределах max_length
        split_index = text.rfind('\n', 0, max_length)
        if split_index == -1:
            # Если перенос строки не найден, разбиваем строго по max_length
            split_index = max_length
        part = text[:split_index]
        parts.append(part)
        text = text[split_index:].lstrip('\n')  # Удаляем начальные переносы строк для следующей части
    if text:
        parts.append(text)
    return parts


async def publish_news():
    loop = asyncio.get_event_loop()
    try:
        config = config_collection.find_one({"_id": "bot_config"})
        news_per_hour = config.get('news_per_hour', 5)  # Значение по умолчанию 5
        # Выполнение блокирующего вызова в отдельном потоке
        new_news = await loop.run_in_executor(None, lambda: list(collection.find({"published": False})))

        news_to_publish = new_news[:news_per_hour] if len(new_news) >= news_per_hour else new_news

        published_count = 0

        if news_to_publish:
            for news in news_to_publish:
                # Получение полей новости
                title = news.get("title", "Без заголовка")
                text_content = news.get("text", "Нет содержания")
                image = news.get("image")  # Ожидается URL изображения
                url = news.get("url")  # Ссылка на источник

                # Формирование ссылки на источник
                if url:
                    source_text = hlink("Источник", url)
                else:
                    source_text = ""

                # Формирование полного текста сообщения
                message_text = f"<b>{title}</b>\n\n{text_content}\n\n{source_text}"

                try:
                    # Если изображение присутствует, пытаемся отправить его первым
                    if image:
                        try:
                            await bot.send_photo(
                                chat_id=CHANNEL_ID,
                                photo=image,
                                caption=f"<b>{title}</b>",
                                parse_mode=ParseMode.HTML  # Используем HTML-разметку
                            )
                            # Отправляем оставшийся текст (text + source)
                            remaining_text = f"{text_content}\n\n{source_text}"
                            if len(remaining_text) > MAX_MESSAGE_LENGTH:
                                message_parts = split_text(remaining_text, MAX_MESSAGE_LENGTH)
                                for part in message_parts:
                                    await bot.send_message(
                                        chat_id=CHANNEL_ID,
                                        text=part,
                                        parse_mode=ParseMode.HTML  # Используем HTML-разметку
                                    )
                            else:
                                await bot.send_message(
                                    chat_id=CHANNEL_ID,
                                    text=remaining_text,
                                    parse_mode=ParseMode.HTML  # Используем HTML-разметку
                                )
                        except Exception as e:
                            error_message = str(e).lower()
                            if "wrong file identifier" in error_message or "http url" in error_message:
                                logger.error(f"Ошибка при отправке изображения для новости '{title}': {e}")
                                logger.info(f"Публикуем новость '{title}' без изображения.")
                                # Публикуем текст без изображения
                                if len(message_text) > MAX_MESSAGE_LENGTH:
                                    message_parts = split_text(message_text, MAX_MESSAGE_LENGTH)
                                    for part in message_parts:
                                        await bot.send_message(
                                            chat_id=CHANNEL_ID,
                                            text=part,
                                            parse_mode=ParseMode.HTML
                                        )
                                else:
                                    await bot.send_message(
                                        chat_id=CHANNEL_ID,
                                        text=message_text,
                                        parse_mode=ParseMode.HTML
                                    )
                            else:
                                # Если ошибка не связана с изображением, повторно выбрасываем исключение
                                raise e
                    else:
                        # Если изображения нет, отправляем весь текст
                        if len(message_text) > MAX_MESSAGE_LENGTH:
                            message_parts = split_text(message_text, MAX_MESSAGE_LENGTH)
                            for part in message_parts:
                                await bot.send_message(
                                    chat_id=CHANNEL_ID,
                                    text=part,
                                    parse_mode=ParseMode.HTML  # Используем HTML-разметку
                                )
                        else:
                            await bot.send_message(
                                chat_id=CHANNEL_ID,
                                text=message_text,
                                parse_mode=ParseMode.HTML  # Используем HTML-разметку
                            )

                    # Обновление поля published на True после успешной отправки
                    await loop.run_in_executor(
                        None,
                        lambda: collection.update_one(
                            {"_id": news["_id"]},
                            {"$set": {"published": True}}
                        )
                    )

                    logger.info(f"Новость '{title}' опубликована.")
                except Exception as e:
                    # Проверка конкретной ошибки о длине сообщения
                    error_message = str(e).lower()
                    if "message is too long" in error_message:
                        logger.warning(f"Новость '{title}' слишком длинная и будет разбита на части.")
                        # Разбиваем сообщение на части
                        message_parts = split_text(message_text, MAX_MESSAGE_LENGTH)
                        for part in message_parts:
                            try:
                                await bot.send_message(
                                    chat_id=CHANNEL_ID,
                                    text=part,
                                    parse_mode=ParseMode.HTML  # Используем HTML-разметку
                                )
                            except Exception as send_error:
                                logger.error(f"Ошибка при отправке части сообщения: {send_error}")
                        # Обновляем поле published после успешной отправки всех частей
                        await loop.run_in_executor(
                            None,
                            lambda: collection.update_one(
                                {"_id": news["_id"]},
                                {"$set": {"published": True}}
                            )
                        )
                        logger.info(f"Новость '{title}' опубликована частями.")
                    else:
                        logger.error(f"Ошибка при публикации новости '{title}': {e}")

                published_count += 1

        stats_collection.insert_one({
            "timestamp": datetime.utcnow(),
            "sent_count": published_count,
            "channel_id": CHANNEL_ID
        })
    except PyMongoError as e:
        logger.error(f"Ошибка при доступе к MongoDB: {e}")


async def scheduled(publish_interval: int):
    while True:
        await publish_news()
        await asyncio.sleep(publish_interval)


@dp.message(Command("start"))
async def cmd_start(message):
    await message.reply("Бот запущен и будет публиковать новости каждые 10 минут.")


ALLOWED_USERS = [416546809]  # Замените на список ID разрешенных пользователей


class AddSourceStates(StatesGroup):
    waiting_for_sources = State()


# Команда для добавления источника
@dp.message(Command("add_sources"))
async def add_source_command(message: Message, state: FSMContext):
    if message.from_user.id not in ALLOWED_USERS:
        await message.reply("У вас нет прав для выполнения этой команды.")
        return

    await message.reply(
        "Пожалуйста, отправьте список источников в формате:\n"
        "<ссылка>  (Название)\n\n"
        "Вы можете отправить один или несколько источников, каждый в новой строке."
    )
    await state.set_state(AddSourceStates.waiting_for_sources)

    # Обработка введенных источников


@dp.message(AddSourceStates.waiting_for_sources)
async def process_sources(message: Message, state: FSMContext):
    sources_text = message.text

    # Разбиваем текст на строки
    lines = sources_text.strip().split('\n')

    # Списки для успешных и неуспешных добавлений
    added_sources = []
    failed_sources = []

    # Регулярное выражение для проверки формата
    pattern = re.compile(r'^(?P<link>\S+)(\s*\+\s*|\s+)\((?P<name>.+?)\)$')

    for line in lines:
        line = line.strip()
        match = pattern.match(line)
        if match:
            link = match.group('link').strip()
            name = match.group('name').strip()
            # Дополнительная проверка корректности ссылки
            if not re.match(r'^https?://', link):
                failed_sources.append(f"{line} (некорректная ссылка)")
                continue
            # Проверяем, существует ли источник уже в базе
            existing_source = sources_collection.find_one({'url': link})
            if existing_source:
                failed_sources.append(f"{link} ({name}) - уже существует")
                continue
            # Добавляем источник в базу данных
            sources_collection.insert_one({"url": link, "name": name, "active": True})
            added_sources.append(f"{link} ({name})")
        else:
            failed_sources.append(f"{line} (неверный формат)")

    # Формируем ответное сообщение
    response_messages = []
    if added_sources:
        response_messages.append("Следующие источники были добавлены и активированы:")
        response_messages.extend(added_sources)
    if failed_sources:
        response_messages.append("\nНе удалось распознать следующие источники:")
        response_messages.extend(failed_sources)

    await message.reply('\n'.join(response_messages))
    # Сбрасываем состояние
    await state.clear()


class SourceCallback(CallbackData, prefix="source"):
    action: str
    source_id: str


@dp.message(Command("manage_sources"))
async def manage_sources(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.reply("У вас нет прав для выполнения этой команды.")
        return

    sources = list(sources_collection.find())
    if not sources:
        await message.reply("Список источников пуст.")
        return

    for source in sources:
        source_id = str(source['_id'])
        source_url = source['url']
        is_active = source.get('active', True)

        status_icon = '✅' if is_active else '🛑'
        status_action = 'deactivate' if is_active else 'activate'

        buttons = [[
            InlineKeyboardButton(
                text=status_icon,
                callback_data=SourceCallback(action=status_action, source_id=source_id).pack()
            ),
            InlineKeyboardButton(
                text='🗑',
                callback_data=SourceCallback(action='delete', source_id=source_id).pack()
            )
        ]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        await message.reply(f"{source_url} ({source['name']})", reply_markup=keyboard)


@dp.callback_query(SourceCallback.filter())
async def process_source_callback(callback_query: CallbackQuery, callback_data: dict):
    if callback_query.from_user.id not in ALLOWED_USERS:
        await callback_query.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
        return
    action = callback_data.action
    source_id = callback_data.source_id
    source = sources_collection.find_one({'_id': ObjectId(source_id)})

    if not source:
        await callback_query.answer("Источник не найден.", show_alert=True)
        return

    source_url = source['url']

    if action == 'activate':
        sources_collection.update_one({'_id': ObjectId(source_id)}, {'$set': {'active': True}})
        await callback_query.answer(f"Источник {source_url} активирован.", show_alert=True)
    elif action == 'deactivate':
        sources_collection.update_one({'_id': ObjectId(source_id)}, {'$set': {'active': False}})
        await callback_query.answer(f"Источник {source_url} деактивирован.", show_alert=True)
    elif action == 'delete':
        sources_collection.delete_one({'_id': ObjectId(source_id)})
        await callback_query.answer(f"Источник {source_url} удалён.", show_alert=True)
        await callback_query.message.delete()
        return

    is_active = action == 'activate'
    status_icon = '✅' if is_active else '🛑'
    status_action = 'deactivate' if is_active else 'activate'

    buttons = [[
        InlineKeyboardButton(
            text=status_icon,
            callback_data=SourceCallback(action=status_action, source_id=source_id).pack()
        ),
        InlineKeyboardButton(
            text='🗑',
            callback_data=SourceCallback(action='delete', source_id=source_id).pack()
        )
    ]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback_query.message.edit_reply_markup(reply_markup=keyboard)


@dp.message(Command("set_news_per_hour"))
async def set_news_per_hour_command(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.reply("У вас нет прав для выполнения этой команды.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        await message.reply("Пожалуйста, укажите количество новостей в час после команды /set_news_per_hour")
        return

    news_per_hour = int(args[1])
    config_collection.update_one(
        {"_id": "bot_config"},
        {"$set": {"news_per_hour": news_per_hour}},
        upsert=True
    )
    await message.reply(f"Количество новостей в час установлено на {news_per_hour}.")


@dp.message(Command("stats"))
async def stats_command(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.reply("У вас нет прав для выполнения этой команды.")
        return

    # Получаем текущую дату и время
    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)

    # Получаем статистику за последний час
    stats = stats_collection.find({"timestamp": {"$gte": one_hour_ago}})

    total_sent = sum(stat['sent_count'] for stat in stats)

    await message.reply(f"За последний час было отправлено {total_sent} новостей.")


async def main():
    # Запуск фоновой задачи
    publish_interval = 10  # 600 секунд = 10 минут
    asyncio.create_task(scheduled(publish_interval))

    # Запуск бота
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        mongo_client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
