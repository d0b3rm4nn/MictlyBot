"""Registro de comandos visibles en el menú de Telegram.

Se aplica con setMyCommands en cada arranque, así la lista queda versionada
en el código. Equivale a /setcommands en @BotFather, que la sobrescribe.
"""

from __future__ import annotations

from telegram import BotCommand, BotCommandScopeDefault
from telegram.ext import Application

COMMANDS: tuple[tuple[str, str], ...] = (
    ("bin", "Consulta un BIN de 6 a 8 dígitos"),
    ("luhn", "Valida el dígito de control de un número"),
    ("start", "Mensaje de bienvenida"),
    ("help", "Ver la ayuda"),
)

SCOPE = BotCommandScopeDefault()


def bot_commands() -> list[BotCommand]:
    return [BotCommand(name, description) for name, description in COMMANDS]


async def register_commands(app: Application) -> None:
    await app.bot.set_my_commands(bot_commands(), scope=SCOPE)
