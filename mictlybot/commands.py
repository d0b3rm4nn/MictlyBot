"""Registro de comandos visibles en el menú de Telegram."""

from __future__ import annotations

from telegram import BotCommand, BotCommandScopeDefault
from telegram.ext import Application

COMMANDS: tuple[tuple[str, str], ...] = (
    ("bin", "Consulta un BIN de 6 a 8 dígitos"),
    ("gen", "Genera tarjetas Luhn-validas desde una plantilla"),
    ("luhn", "Valida el dígito de control"),
    ("check", "Prueba una tarjeta contra Stripe"),
    ("target", "Lista los perfiles configurados"),
    ("start", "Mensaje de bienvenida"),
    ("help", "Ver la ayuda"),
)

SCOPE = BotCommandScopeDefault()


def bot_commands() -> list[BotCommand]:
    return [BotCommand(name, description) for name, description in COMMANDS]


async def register_commands(app: Application) -> None:
    await app.bot.set_my_commands(bot_commands(), scope=SCOPE)
