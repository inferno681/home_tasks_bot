import logging

from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.pymongo import PyMongoStorage
from aiogram.fsm.storage.redis import RedisStorage

from bot.db import client as mongo_client
from config.config import config

logger = logging.getLogger(__name__)


def build_fsm_storage() -> BaseStorage:
    """Build the FSM storage backend selected via config.fsm.storage."""
    logger.info(f"FSM storage: {config.fsm.storage}")
    if config.fsm.storage == "redis":
        return RedisStorage.from_url(config.redis_url)
    if config.fsm.storage == "mongo":
        # Переиспользует уже открытое соединение к Atlas (bot/db.py), а не
        # плодит второй клиент — просто отдельная коллекция в той же БД.
        return PyMongoStorage(
            client=mongo_client,
            db_name=config.mongodb.db,
            collection_name=config.fsm.mongo_collection,
        )
    return MemoryStorage()
