from aiogram import BaseMiddleware
from aiogram.types import Message

class ResetFSMOnCommandMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        """
        event = Message | CallbackQuery
        data['state'] = FSMContext
        """
        if isinstance(event, Message):
            text = event.text or ""
            # Проверим, является ли это командой
            # (простая проверка на '/',
            #  или можно использовать aiogram.filters.Command)
            if text.startswith('/'):
                # Сбросим состояние
                state = data['state']
                await state.clear()
        return await handler(event, data)
