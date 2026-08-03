import logging

from beanie import init_beanie
from pymongo import AsyncMongoClient

from bot.models import Pool, Task, User
from config.config import config

logger = logging.getLogger(__name__)

client: AsyncMongoClient = AsyncMongoClient(
    config.secrets.mongo_uri.get_secret_value()
)


async def init_db() -> None:
    """Подключает Beanie (ODM поверх async-драйвера PyMongo) к Atlas."""
    await init_beanie(
        database=client[config.mongodb.db],
        document_models=[Task, User, Pool],
    )
    logger.info(f"Connected to MongoDB, db={config.mongodb.db!r}")
