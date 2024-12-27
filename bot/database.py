# database.py

import pymongo
from config import (
    MONGODB_HOST,
    MONGODB_USER,
    MONGODB_PASS,
    MONGODB_DBNAME,
    MONGODB_AUTH_DB,
    DEFAULT_CONFIG,
    DATABASE_NAME,
    COLLECTION_NAME,
    logger
)

# Инициализация клиента
mongo_client = pymongo.MongoClient(
    MONGODB_HOST,
    username=MONGODB_USER,
    password=MONGODB_PASS,
    authSource=MONGODB_AUTH_DB,
    authMechanism='SCRAM-SHA-256'
)

# Получаем ссылку на базу данных
db = mongo_client[DATABASE_NAME]

# Коллекции
collection = db[COLLECTION_NAME]
sources_collection = db["sources"]
keywords_collection = db["keywords"]
bans_collection = db["bans"]
config_collection = db["config"]
stats_collection = db["statistics"]

# Убеждаемся, что конфиг бота есть в БД
config_collection.update_one(
    {"_id": "bot_config"},
    {"$setOnInsert": DEFAULT_CONFIG},
    upsert=True
)
