import os
import uuid

import pytest
import pytest_asyncio
from beanie import init_beanie
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

# config/config.py builds an AppConfig singleton at import time, which
# requires BOT_TOKEN/MONGO_URI to be present. Tests shouldn't need a real
# .env, so seed harmless placeholders before any test module imports it.
os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("MONGO_URI", "mongodb://localhost/test")

from bot.models import Pool, Task, User  # noqa: E402 (env vars first)

TEST_MONGO_URI = os.environ.get("TEST_MONGO_URI", "mongodb://localhost:27017")


@pytest_asyncio.fixture(scope="session")
async def mongo_db():
    """Real MongoDB database for integration tests.

    Skips (not fails) any test that requests this fixture if no MongoDB is
    reachable — CI provides one as a service container (see
    .github/workflows/main.yml), locally it's opt-in.
    """
    client: AsyncMongoClient = AsyncMongoClient(
        TEST_MONGO_URI, serverSelectionTimeoutMS=1500
    )
    db_name = f"home_tasks_test_{uuid.uuid4().hex[:8]}"
    try:
        await client.admin.command("ping")
    except PyMongoError:
        await client.close()
        pytest.skip(f"no MongoDB reachable at {TEST_MONGO_URI}")

    db = client[db_name]
    await init_beanie(database=db, document_models=[Task, User, Pool])
    yield db
    await client.drop_database(db_name)
    await client.close()


@pytest_asyncio.fixture
async def clean_db(mongo_db):
    """Empty the tasks/users/pools collections before an isolated test."""
    await Task.delete_all()
    await User.delete_all()
    await Pool.delete_all()
    yield
