# main.py

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from middlewares.reset_fsm_state import ResetFSMOnCommandMiddleware
from config import BOT_TOKEN, logger
from database import mongo_client  # чтобы потом закрыть при завершении
from scheduled_job import scheduled
from routers import main_router

# Чтобы в scheduled_job использовать bot, сделаем его глобальным
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")


async def main():
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(main_router)
    dp.message.middleware(ResetFSMOnCommandMiddleware())

    # Запускаем фоновой таск
    asyncio.create_task(scheduled(bot, ))

    # Запускаем бота
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
