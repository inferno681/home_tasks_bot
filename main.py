import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.pymongo import PyMongoStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import (
    SimpleRequestHandler,
    setup_application,
)
from aiohttp import web

from bot.db import init_db
from bot.fsm_storage import build_fsm_storage
from bot.handlers import (
    admin,
    common,
    edit_task,
    history,
    list_tasks,
    new_task,
    pools,
    settings,
)
from bot.middlewares import UserTrackerMiddleware
from bot.scheduler import setup_scheduler
from config.config import config
from config.logger import configure_logging

logger = logging.getLogger(__name__)


def setup_bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    """Create the Bot and Dispatcher, wire routers and middleware."""
    dp = Dispatcher(storage=build_fsm_storage())
    dp.update.outer_middleware(UserTrackerMiddleware())

    dp.include_router(common.router)
    dp.include_router(new_task.router)
    dp.include_router(list_tasks.router)
    dp.include_router(history.router)
    dp.include_router(edit_task.router)
    dp.include_router(pools.router)
    dp.include_router(settings.router)
    dp.include_router(admin.router)

    bot = Bot(token=config.secrets.bot_token.get_secret_value())
    return bot, dp


async def on_startup(bot: Bot) -> None:
    """Register the webhook with Telegram."""
    await bot.set_webhook(
        config.webhook_url,
        secret_token=config.secrets.webhook_secret.get_secret_value(),
    )


async def create_app(bot: Bot, dp: Dispatcher) -> web.Application:
    """Build the aiohttp app that receives Telegram webhook updates."""
    dp.startup.register(on_startup)

    app = web.Application()
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=config.secrets.webhook_secret.get_secret_value(),
    ).register(app, path=config.service.webhook_path)
    setup_application(app, dp, bot=bot)
    return app


async def start_polling(bot: Bot, dp: Dispatcher) -> None:
    """Run the bot with long polling."""
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, close_bot_session=False)


async def start_webhook(bot: Bot, dp: Dispatcher) -> None:
    """Run the bot behind an aiohttp webhook server."""
    app = await create_app(bot, dp)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(
        runner,
        host=config.service.web_server_host,
        port=config.service.web_server_port,
    )
    await site.start()
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


async def main():
    configure_logging()

    await init_db()

    bot, dp = setup_bot_and_dispatcher()
    # RedisStorage.from_url() не подключается сразу — без явного ping
    # неверный fsm.redis.host всплыл бы только на первом /start пользователя
    # после деплоя, а не при старте контейнера.
    if isinstance(dp.storage, RedisStorage):
        await dp.storage.redis.ping()

    scheduler = setup_scheduler(bot)
    scheduler.start()

    mode = "webhook" if config.service.webhook else "polling"
    logger.info(f"Starting home-tasks-bot in {mode} mode")

    try:
        if config.service.webhook:
            await start_webhook(bot, dp)
        else:
            await start_polling(bot, dp)
    finally:
        logger.info("Shutting down")
        # AsyncIOExecutor.shutdown() не умеет реально ждать job (см. его
        # исходник: `wait` игнорируется, pending futures отменяются всегда) —
        # поэтому с fsm.storage=mongo намеренно НЕ закрываем storage: это
        # закрыло бы общий с bot/db.py клиент прямо под отменённым
        # check_reminders. Процесс всё равно завершается следом.
        scheduler.shutdown(wait=False)
        if not isinstance(dp.storage, PyMongoStorage):
            await dp.storage.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
