# routers/__init__.py

from aiogram import Router

from .commands import commands_router
from .manage_sources import manage_sources_router
from .manage_keywords import manage_keywords_router
from .manage_bans import manage_bans_router

# Если нужны еще роутеры, подключаем их также

main_router = Router()
main_router.include_router(commands_router)
main_router.include_router(manage_sources_router)
main_router.include_router(manage_keywords_router)
main_router.include_router(manage_bans_router)
