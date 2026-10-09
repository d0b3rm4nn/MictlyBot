"""Handlers de Telegram."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from .binlist import (
    BinError,
    BinListClient,
    BinNotFound,
    BinRateLimited,
    normalize_bin,
)
from .formatter import format_bin
from .luhn import check_card
from .ratelimit import RateLimiter

log = logging.getLogger(__name__)

USAGE = (
    "**Uso:** `/bin 123456`\n"
    "También acepta 6, 7 u 8 dígitos (los que prefieras del prefijo)."
)

HELP = (
    "🤖 **MictlyBot** — consulta metadatos de un BIN.\n\n"
    "Comandos:\n"
    "`/bin <6-8 dígitos>` — busca banco, país, marca y tipo\n"
    "`/luhn <número>` — valida el dígito de control de un número\n"
    "`/start` — mensaje de bienvenida\n"
    "`/help` — esta ayuda\n\n"
    "_Sobre `/luhn`: solo comprueba el dígito de control para detectar "
    "errores de tecleo. El número no se guarda ni se registra._\n\n"
    "_Los datos vienen de BinList (lookup.binlist.net), una fuente pública._"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP)


async def luhn_checker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    parts = (update.message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text(
            "❌ **Uso:** `/luhn 4539578763621486`\n"
            "_Solo valida el dígito de control; el número no se almacena._",
            parse_mode="Markdown",
        )
        return

    valid, reason = check_card(parts[1])
    if valid:
        text = "✅ **Dígito de control válido**\nEl número está bien formado."
    else:
        text = f"❌ **Número inválido**\n{reason}"
    footer: str = context.bot_data["footer"]
    await update.message.reply_text(text + footer, parse_mode="Markdown")


async def bin_checker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    limiter: RateLimiter = context.bot_data["rate_limiter"]
    client: BinListClient = context.bot_data["bin_client"]
    footer: str = context.bot_data["footer"]

    allowed, retry_after = limiter.allow(update.effective_user.id)
    if not allowed:
        await update.message.reply_text(
            f"⏳ Vas muy rápido. Espera {retry_after:.0f} s e inténtalo de nuevo.",
            parse_mode="Markdown",
        )
        return

    parts = (update.message.text or "").split()
    if len(parts) < 2:
        await update.message.reply_text("❌ " + USAGE, parse_mode="Markdown")
        return

    try:
        bin_number = normalize_bin(parts[1])
    except ValueError:
        await update.message.reply_text(
            "❌ Necesito entre 6 y 8 dígitos. Ejemplo: `/bin 123456`",
            parse_mode="Markdown",
        )
        return

    waiting = await update.message.reply_text(
        f"📡 Consultando en **BinList** para: `{bin_number}`...",
        parse_mode="Markdown",
    )

    try:
        info, from_cache = await client.lookup(bin_number)
        text = format_bin(info, from_cache, footer)
    except BinRateLimited as exc:
        text = f"⚠️ **Límite de API:** {exc}"
    except BinNotFound as exc:
        text = f"❌ {exc}"
    except BinError as exc:
        text = f"⚠️ {exc}"
    except Exception:
        log.exception("Fallo inesperado en lookup de %s", bin_number)
        text = "⚠️ Error interno. Inténtalo más tarde."

    await waiting.edit_text(text, parse_mode="Markdown")
