import os

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Токен вашего бота
CHANNEL_ID = os.getenv("CHANNEL_ID")  # ID вашего канала, например, -1001234567890
MONGODB_URI = os.getenv("MONGODB_URI")  # URI для подключения к MongoDB
DATABASE_NAME = os.getenv("DATABASE_NAME", "news_db")  # Название базы данных
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "news")  # Название коллекции
