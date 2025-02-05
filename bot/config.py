import logging

BOT_TOKEN = "7728371504:AAE9OKYCW5MVBYPB-nNJn60BZTk3viOxlzA"
CHANNEL_ID = "-1002370678576"

ALL_CHANNELS = ["-1002370678576", "-1002454852648"]

MONGODB_HOST = "194.87.186.63"
MONGODB_USER = "Admin"
MONGODB_PASS = "PasswordForMongo63"
MONGODB_DBNAME = "news_db"
MONGODB_AUTH_DB = "admin"

DATABASE_NAME = "news_db"
COLLECTION_NAME = "articles"

# Допустимые пользователи
ALLOWED_USERS = [416546809, 282247284, 5257246969, 667847105, 81209035]

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройки по умолчанию
DEFAULT_CONFIG = {
    "_id": "bot_config",
    "news_per_hour": 5,
    "publish_interval": 3600,
    "max_news_length": 4096
}

CUSTOM_TITLE_SOURCES = {
    # Ключ — это точное значение поля news["title"]
    "Управление сельского хозяйства Липецкой области": "FIRST_SENTENCE",
    # "Название другого источника": "FIRST_SENTENCE",
}
