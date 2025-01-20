# scheduled_job.py

import asyncio
import re
from datetime import datetime
from config import CHANNEL_ID, logger
from database import collection, config_collection

from misc import get_effective_title, flexible_truncate_text_by_delimiters, remove_first_sentence_if_in_title, \
    remove_publication_date_lines, remove_custom_fragments, compress_newlines, extract_and_remove_first_sentence, \
    join_single_word_lines

# либо передавать его в функцию scheduled как параметр
MAX_MESSAGE_LENGTH = 4096  # fallback, если не найдёт в конфиге


async def publish_single_news(news, bot):
    config = config_collection.find_one({"_id": "bot_config"})
    max_news_length = config.get('max_news_length', MAX_MESSAGE_LENGTH)

    # Убрали пока заголовки пока будет только первое предложение
    title = get_effective_title(news)
    text_content = news.get("text", "Нет содержания")

    # --- 1) Удаляем из текста первое предложение, если оно уже в заголовке ---
    # text_content = remove_first_sentence_if_in_title(text_content, title)

    # --- 2) Удаляем "дату публикации", если она отдельной строкой в начале/конце ---
    text_content = remove_publication_date_lines(text_content)

    text_content = remove_custom_fragments(text_content)

    text_content = compress_newlines(text_content)

    text_content = join_single_word_lines(text_content)

    image = news.get("image")  # URL изображения
    url = news.get("url")  # Ссылка на источник

    if url:
        first_sentence, remainder = extract_and_remove_first_sentence(text_content)
        linked_first = f'<a href="{url}">{first_sentence}</a>'
        # Собираем обратно
        text_content = linked_first + ' ' + remainder.strip()
    else:
        # Если URL нет, ничего не делаем, текст остаётся как есть
        pass

    tags = " ".join(
        f"#{word.replace(' ', '_')}"
        for word in news.get("found_keywords", [])
    )

    full_text = text_content

    if len(full_text) > max_news_length:
        full_text = flexible_truncate_text_by_delimiters(full_text, max_news_length)
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
