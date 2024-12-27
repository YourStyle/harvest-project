# scheduled_job.py

import asyncio
import re
from datetime import datetime
from config import CHANNEL_ID, logger
from database import collection, config_collection

from misc import get_effective_title

# либо передавать его в функцию scheduled как параметр
MAX_MESSAGE_LENGTH = 4096  # fallback, если не найдёт в конфиге


# Функция для обрезки текста
def truncate_text(news_text, max_length):
    if len(news_text) <= max_length:
        return news_text

    sentence_endings = [m.end() for m in re.finditer(r'[.;]', news_text)]
    valid_endings = [pos for pos in sentence_endings if pos <= max_length]

    if valid_endings:
        cut_off = valid_endings[-1]
        truncated = news_text[:cut_off]
    else:
        truncated = news_text[:max_length]

    return truncated.strip()


async def publish_single_news(news, bot):
    config = config_collection.find_one({"_id": "bot_config"})
    max_news_length = config.get('max_news_length', MAX_MESSAGE_LENGTH)

    title = get_effective_title(news)
    text_content = news.get("text", "Нет содержания")
    image = news.get("image")  # URL изображения
    url = news.get("url")  # Ссылка на источник

    if url:
        source_text = f'<a href="{url}">Источник</a>'
        read_more_link = f'<a href="{url}">"{title}"</a>'
    else:
        source_text = ""
        read_more_link = ""

    tags = " ".join(f"#{word}" for word in list(news.get("found_keywords", [])))

    full_text = f"<b>{title}</b>\n{text_content}\n\n{tags}\n\n{source_text}"

    if len(full_text) > max_news_length:
        # Обрезаем текст (учитываем ссылку)
        allowed_length = max_news_length - len(read_more_link)
        truncated_text = truncate_text(
            text_content,
            allowed_length - len(f"<b>{title}</b>\n\n")
        )
        full_text = f"<b>{read_more_link}</b>\n\n{truncated_text}\n\n{tags}"

    try:
        # Публикуем
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
                # Если ошибка связана с URL изображения, публикуем без картинки
                if "http url content" in error_message or "wrong file identifier" in error_message:
                    logger.error(f"Ошибка при отправке изображения для новости '{title}': {e}")
                    logger.info(f"Публикуем новость '{title}' без изображения.")
                    await bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=full_text,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                else:
                    raise e
        else:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=full_text,
                parse_mode='HTML',
                disable_web_page_preview=True
            )

        # Отмечаем новость как опубликованную
        collection.update_one(
            {"_id": news["_id"]},
            {"$set": {"published": True}}
        )

        logger.info(f"Новость '{title}' опубликована.")
    except Exception as e:
        logger.error(f"Ошибка при публикации новости '{title}': {e}")


async def scheduled(bot):
    """
    Запускается в виде фоновой задачи из main.py
    Периодически публикует новости в канал
    """
    while True:
        config = config_collection.find_one({"_id": "bot_config"})
        news_per_interval = config.get('news_per_hour', 5)
        publish_interval = config.get('publish_interval', 3600)

        if news_per_interval <= 0 or publish_interval <= 0:
            logger.warning("Лимит новостей или интервал публикации <= 0. Повтор через 60 сек.")
            await asyncio.sleep(60)
            continue

        # Сбрасываем published_count в конфиге
        config_collection.update_one(
            {"_id": "bot_config"},
            {"$set": {"published_count": 0}}
        )
        published_count = 0
        interval_between_news = publish_interval / news_per_interval
        cycle_start_time = datetime.utcnow()

        while published_count < news_per_interval:
            news = collection.find_one({"published": False})
            if news:
                try:
                    await publish_single_news(news, bot)
                    published_count += 1
                    config_collection.update_one(
                        {"_id": "bot_config"},
                        {"$set": {"published_count": published_count}}
                    )
                except Exception as e:
                    logger.info(f"Не смогли опубликовать новость. Причина: {e}")
                    published_count += 1
                    config_collection.update_one(
                        {"_id": "bot_config"},
                        {"$set": {"published_count": published_count}}
                    )
            else:
                logger.info("Нет больше новостей для публикации.")
                break

            await asyncio.sleep(interval_between_news)

        # Ждём до следующего цикла
        time_passed = (datetime.utcnow() - cycle_start_time).total_seconds()
        time_to_wait = publish_interval - time_passed
        if time_to_wait > 0:
            logger.info(f"Ждем {time_to_wait} секунд до следующего цикла публикации.")
            await asyncio.sleep(time_to_wait)
