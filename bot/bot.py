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

BOT_TOKEN = "7728371504:AAE9OKYCW5MVBYPB-nNJn60BZTk3viOxlzA"
CHANNEL_ID = "-1002370678576"
MONGODB_URI = "mongodb://Admin:PasswordForMongo63@194.87.186.63/admin?authMechanism=SCRAM-SHA-256"
DATABASE_NAME = "news_db"
COLLECTION_NAME = "articles"

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация MongoDB клиента
mongo_client = pymongo.MongoClient("194.87.186.63", username='Admin', password='PasswordForMongo63',
                                   authSource='admin', authMechanism='SCRAM-SHA-256')
db = mongo_client[DATABASE_NAME]
collection = db[COLLECTION_NAME]
sources_collection = db['sources']
keywords_collection = db['keywords']
config_collection = db['config']

stats_collection = db['statistics']

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Максимальная длина сообщения Telegram
MAX_MESSAGE_LENGTH = 4096

default_config = {
    "_id": "bot_config",
    "news_per_hour": 5,  # Значение по умолчанию
    "publish_interval": 3600,  # Значение по умолчанию в секундах (1 час)
    "max_news_length": 4096  # Максимальная длина текста новости по умолчанию
}

config_collection.update_one(
    {"_id": "bot_config"},
    {"$setOnInsert": default_config},
    upsert=True
)


def truncate_text(news_text, max_length):
    if len(news_text) <= max_length:
        return news_text

    # Находим позиции возможных окончаний предложений
    sentence_endings = [m.end() for m in re.finditer(r'[.;]', news_text)]
    # Оставляем только те окончания, которые находятся в пределах max_length
    valid_endings = [pos for pos in sentence_endings if pos <= max_length]

    if valid_endings:
        # Обрезаем текст по последнему подходящему окончанию предложения
        cut_off = valid_endings[-1]
        truncated = news_text[:cut_off]
    else:
        # Если нет подходящего окончания, просто обрезаем текст
        truncated = news_text[:max_length]

    return truncated.strip()


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


async def publish_single_news(news):
    config = config_collection.find_one({"_id": "bot_config"})
    max_news_length = config.get('max_news_length', 4096)

    title = news.get("title", "Без заголовка")
    text_content = news.get("text", "Нет содержания")
    image = news.get("image")  # Ожидается URL изображения
    url = news.get("url")  # Ссылка на источник

    # Формирование ссылки на источник
    if url:
        source_text = f'<a href="{url}">Источник</a>'
        read_more_link = f'\n\n<a href="{url}">Далее...</a>'
    else:
        source_text = ""
        read_more_link = ""

    # Объединяем заголовок и текст
    full_text = f"<b>{title}</b>\n\n{text_content}\n\n{source_text}"

    # Проверяем длину текста
    if len(full_text) > max_news_length:
        # Обрезаем текст по последнему вмещающемуся предложению
        allowed_length = max_news_length - len(read_more_link)
        truncated_text = truncate_text(text_content, allowed_length - len(f"<b>{title}</b>\n\n"))
        full_text = f"<b>{title}</b>\n\n{truncated_text}{read_more_link}"

    try:
        # Отправляем сообщение
        if image:
            try:
                await bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=full_text,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            except Exception as e:
                error_message = str(e).lower()
                if "http url content" in error_message or "wrong file identifier" in error_message or "http url specified" in error_message:
                    logger.error(f"Ошибка при отправке изображения для новости '{title}': {e}")
                    logger.info(f"Публикуем новость '{title}' без изображения.")
                    # Отправляем новость без изображения
                    await bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=full_text,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                else:
                    # Если ошибка не связана с изображением, повторно выбрасываем исключение
                    raise e
        else:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=full_text,
                parse_mode='HTML',
                disable_web_page_preview=True
            )

        # Обновление поля published на True после успешной отправки
        collection.update_one(
            {"_id": news["_id"]},
            {"$set": {"published": True}}
        )

        logger.info(f"Новость '{title}' опубликована.")
    except Exception as e:
        logger.error(f"Ошибка при публикации новости '{title}': {e}")


async def scheduled():
    while True:
        # Загружаем настройки из базы данных
        config = config_collection.find_one({"_id": "bot_config"})
        news_per_interval = config.get('news_per_hour', 5)
        publish_interval = config.get('publish_interval', 3600)
        max_news_length = config.get('max_news_length', MAX_MESSAGE_LENGTH)
        # Получаем счетчик опубликованных новостей
        published_count = 0  # Обнуляем локальный счетчик

        if news_per_interval <= 0 or publish_interval <= 0:
            logger.warning(
                "Лимит новостей или интервал публикации установлен в 0 или меньше. Ждем 60 секунд перед повторной проверкой.")
            await asyncio.sleep(60)
            continue

        # Сбрасываем счетчик опубликованных новостей в конфиге
        config_collection.update_one(
            {"_id": "bot_config"},
            {"$set": {"published_count": 0}}
        )

        # Вычисляем интервал между публикациями
        interval_between_news = publish_interval / news_per_interval

        # Время начала цикла
        cycle_start_time = datetime.utcnow()

        # Публикуем новости с заданным интервалом
        while published_count < news_per_interval:
            # Получаем следующую новость для публикации
            news = collection.find_one({"published": False})
            if news:
                try:
                    await publish_single_news(news)
                    published_count += 1

                    # Обновляем published_count в конфиге
                    config_collection.update_one(
                        {"_id": "bot_config"},
                        {"$set": {"published_count": published_count}}
                    )
                except Exception as e:
                    logger.info(f"Не смогли опубликовать новость. Причина: {e}")
                    published_count += 1

                    # Обновляем published_count в конфиге
                    config_collection.update_one(
                        {"_id": "bot_config"},
                        {"$set": {"published_count": published_count}}
                    )
            else:
                # Нет больше новостей для публикации
                logger.info("Нет больше новостей для публикации.")
                break

            # Ждем интервал между публикациями
            await asyncio.sleep(interval_between_news)

        # Ждем до следующего цикла
        time_passed = (datetime.utcnow() - cycle_start_time).total_seconds()
        time_to_wait = publish_interval - time_passed
        if time_to_wait > 0:
            logger.info(f"Ждем {time_to_wait} секунд до следующего цикла публикации.")
            await asyncio.sleep(time_to_wait)


@dp.message(Command("start"))
async def cmd_start(message):
    await message.reply("Бот запущен и будет публиковать новости каждые 10 минут.")


ALLOWED_USERS = [416546809, 282247284]  # Замените на список ID разрешенных пользователей


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


class AddKeywordsStates(StatesGroup):
    waiting_for_keywords = State()

@dp.message(Command("add_keywords"))
async def add_keywords_command(message: Message, state: FSMContext):
    if message.from_user.id not in ALLOWED_USERS:
        await message.reply("У вас нет прав для выполнения этой команды.")
        return

    await message.reply(
        "Пожалуйста, отправьте список ключевых слов:\n"
        "слово\n\n"
        "Вы можете отправить один или несколько ключевых слов, каждый в новой строке."
    )
    await state.set_state(AddKeywordsStates.waiting_for_keywords)


# Обработка введенных источников
@dp.message(AddKeywordsStates.waiting_for_keywords)
async def process_sources(message: Message, state: FSMContext):
    sources_text = message.text

    # Разбиваем текст на строки
    lines = sources_text.strip().split('\n')

    # Списки для успешных и неуспешных добавлений
    added_keywords = []
    failed_keywords = []


    for line in lines:
        line = line.strip()

        existing_keyword = keywords_collection.find_one({'keyword': line})
        if existing_keyword:
            failed_keywords.append(f"{line} - уже существует")
            continue
        # Добавляем источник в базу данных
        keywords_collection.insert_one({'keyword': line})
        added_keywords.append(f"{line}")

    # Формируем ответное сообщение
    response_messages = []
    if added_keywords:
        response_messages.append("Следующие источники были добавлены и активированы:")
        response_messages.extend(added_keywords)
    if failed_keywords:
        response_messages.append("\nНе удалось распознать следующие источники:")
        response_messages.extend(failed_keywords)

    await message.reply('\n'.join(response_messages))
    # Сбрасываем состояние
    await state.clear()


class KeywordCallback(CallbackData, prefix="keyword"):
    action: str
    keyword_id: str


@dp.message(Command("manage_keywords"))
async def manage_keywords(message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.reply("У вас нет прав для выполнения этой команды.")
        return

    keywords = list(keywords_collection.find())
    if not keywords:
        await message.reply("Список ключевых слов пуст.")
        return

    for keyword in keywords:
        source_id = str(keywords['_id'])
        keywords_text = keyword['keyword']

        buttons = [[
            InlineKeyboardButton(
                text='🗑',
                callback_data=SourceCallback(action='delete', source_id=source_id).pack()
            )
        ]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        await message.reply(f"{keyword}", reply_markup=keyboard)


@dp.callback_query(KeywordCallback.filter())
async def process_source_callback(callback_query: CallbackQuery, callback_data: dict):
    if callback_query.from_user.id not in ALLOWED_USERS:
        await callback_query.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
        return
    keyword_id = callback_data.keyword_id
    keyword = keywords_collection.find_one({'_id': ObjectId(keyword_id)})

    if not keyword:
        await callback_query.answer("Источник не найден.", show_alert=True)
        return
    keyword_text = keyword['keyword']
    sources_collection.delete_one({'_id': ObjectId(keyword_id)})
    await callback_query.answer(f"Ключевое слово '{keyword_text}' удалено.", show_alert=True)
    await callback_query.message.delete()


class SetPublishIntervalState(StatesGroup):
    waiting_for_interval = State()


@dp.message(Command("set_publish_interval"))
async def set_publish_interval_command(message: Message, state: FSMContext):
    if message.from_user.id not in ALLOWED_USERS:
        await message.reply("У вас нет прав для выполнения этой команды.")
        return

    await message.reply("Пожалуйста, введите интервал публикации в секундах:")
    await state.set_state(SetPublishIntervalState.waiting_for_interval)


@dp.message(SetPublishIntervalState.waiting_for_interval)
async def process_publish_interval(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.reply("Пожалуйста, введите корректное число (интервал в секундах).")
        return

    publish_interval = int(message.text)
    if publish_interval <= 0:
        await message.reply("Интервал публикации должен быть больше нуля.")
        return
    config_collection.update_one(
        {"_id": "bot_config"},
        {"$set": {"publish_interval": publish_interval}},
        upsert=True
    )
    await message.reply(f"Интервал публикации установлен на {publish_interval} секунд.")
    await state.clear()


class SetMaxNewsLengthState(StatesGroup):
    waiting_for_length = State()


@dp.message(Command("set_max_news_length"))
async def set_max_news_length_command(message: Message, state: FSMContext):
    if message.from_user.id not in ALLOWED_USERS:
        await message.reply("У вас нет прав для выполнения этой команды.")
        return

    await message.reply("Пожалуйста, введите максимальную длину текста новости (в символах):")
    await state.set_state(SetMaxNewsLengthState.waiting_for_length)


@dp.message(SetMaxNewsLengthState.waiting_for_length)
async def process_max_news_length(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.reply("Пожалуйста, введите корректное число.")
        return

    max_news_length = int(message.text)
    if max_news_length <= 0 or max_news_length > 4096:
        await message.reply("Длина новости должна быть больше 0 и меньше или равна 4096 символам.")
        return

    config_collection.update_one(
        {"_id": "bot_config"},
        {"$set": {"max_news_length": max_news_length}},
        upsert=True
    )
    await message.reply(f"Максимальная длина текста новости установлена на {max_news_length} символов.")
    await state.clear()


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
    asyncio.create_task(scheduled())

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
