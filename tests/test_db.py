from unittest.mock import AsyncMock, patch

from bot.db import init_db
from bot.models import Pool, Task, User


async def test_init_db_registers_every_document_model():
    """Regression: Pool was missing from document_models here (it was only
    registered in tests/conftest.py's separate init_beanie call), so every
    Pool.find/Pool.get in production raised AttributeError: members the
    moment a real user touched /settings, /pools, /newpool, /invite,
    /leave, /kick, or the pool step in /new."""
    with patch("bot.db.init_beanie", new=AsyncMock()) as mocked_init_beanie:
        await init_db()
        registered = mocked_init_beanie.await_args.kwargs["document_models"]

    assert set(registered) == {Task, User, Pool}
