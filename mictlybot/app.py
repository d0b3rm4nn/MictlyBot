"""Arranque de la aplicación."""

from __future__ import annotations

import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from .binlist import BinListClient
from .commands import register_commands
from .config import load_config
from .handlers import bin_checker, help_cmd, luhn_checker, start
from .ratelimit import RateLimiter
from .sqlite_cache import SQLiteCache


def build_application() -> Application:
    config = load_config()
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    # httpx registra la URL completa de cada request, incluida la del token
    # de Telegram (/bot<TOKEN>/getUpdates). Silenciamos su logger.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    cache = SQLiteCache(config.cache_db_path, config.cache_ttl_seconds)
    bin_client = BinListClient(cache=cache, user_agent=config.user_agent)

    app = Application.builder().token(config.token).build()
    app.bot_data["bin_client"] = bin_client
    app.bot_data["rate_limiter"] = RateLimiter(config.rate_limit_per_minute)
    app.bot_data["footer"] = config.footer

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("bin", bin_checker))
    app.add_handler(CommandHandler("luhn", luhn_checker))
    app.add_handler(MessageHandler(filters.Regex(r"^\.bin\s+"), bin_checker))

    async def post_shutdown(_: Application) -> None:
        await bin_client.aclose()
        cache.close()

    app.post_init = register_commands
    app.post_shutdown = post_shutdown

    return app


def run() -> None:
    app = build_application()
    logging.info("Bot iniciado: BinList + caché persistente")
    app.run_polling()
