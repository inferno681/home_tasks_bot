from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.pymongo import PyMongoStorage
from aiogram.fsm.storage.redis import RedisStorage

from bot.fsm_storage import build_fsm_storage
from config.config import config


def test_memory_backend(monkeypatch):
    monkeypatch.setattr(config.fsm, "storage", "memory")
    assert isinstance(build_fsm_storage(), MemoryStorage)


def test_mongo_backend(monkeypatch):
    monkeypatch.setattr(config.fsm, "storage", "mongo")
    assert isinstance(build_fsm_storage(), PyMongoStorage)


def test_redis_backend(monkeypatch):
    monkeypatch.setattr(config.fsm, "storage", "redis")
    assert isinstance(build_fsm_storage(), RedisStorage)
