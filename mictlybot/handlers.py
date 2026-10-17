"""Handlers de Telegram."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from . import proxy as proxy_mod
from .binlist import (
    BinError,
    BinInfo,
    BinListClient,
    BinNotFound,
    BinRateLimited,
    normalize_bin,
)
from .cardcheck import CardData
from .cardcheck import check_card as check_stripe
from .formatter import format_bin, format_check, format_targets
from .luhn import check_card
from .ratelimit import RateLimiter
from .targets import TargetError, TargetRegistry

log = logging.getLogger(__name__)

USAGE = (
    "**Uso:** `/bin 123456`\n"
    "También acepta 6, 7 u 8 dígitos (los que prefieras del prefijo)."
)

USAGE_CHECK = (
    "**Uso:** `/check 4571736012345678|12|2028|123 [target]`\n"
    "El target es opcional; si lo omites se usa el perfil por defecto."
)

HELP = (
    "🤖 **MictlyBot** — metadatos de BIN y chequeo de tarjetas.\n\n"
    "Comandos:\n"
    "`/bin <6-8 dígitos>` — busca banco, país, marca y tipo\n"
    "`/luhn <número>` — valida el dígito de control\n"
    "`/check <cc|mm|aa|cvv> [target]` — prueba la tarjeta contra Stripe\n"
    "`/target` — lista los perfiles configurados\n"
    "`/start` — mensaje de bienvenida\n"
    "`/help` — esta ayuda\n\n"
    "_Atajos sin slash: `.bin`, `.luhn`, `.check`_\n\n"
    "_`/luhn` solo comprueba el dígito de control. `/check` sí envía el número "
    "completo, así que ese no lo puedes sacar de la caché._"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP, parse_mode="Markdown")


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


async def check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    limiter: RateLimiter = context.bot_data["check_limiter"]
    registry: TargetRegistry = context.bot_data["targets"]
    bin_client: BinListClient = context.bot_data["bin_client"]
    pool: proxy_mod.ProxyPool = context.bot_data["proxy_pool"]
    footer: str = context.bot_data["footer"]
    timeout: float = context.bot_data["http_timeout"]

    allowed, retry_after = limiter.allow(update.effective_user.id)
    if not allowed:
        await update.message.reply_text(
            f"⏳ Vas muy rápido. Espera {retry_after:.0f} s e inténtalo de nuevo.",
            parse_mode="Markdown",
        )
        return

    parts = (update.message.text or "").split()
    if len(parts) < 2:
        await update.message.reply_text("❌ " + USAGE_CHECK, parse_mode="Markdown")
        return

    target_name = parts[2] if len(parts) > 2 else None

    try:
        card = CardData.parse(parts[1])
    except ValueError as exc:
        await update.message.reply_text(
            f"❌ {exc}\n{USAGE_CHECK}", parse_mode="Markdown"
        )
        return

    try:
        target = registry.get(target_name)
    except TargetError as exc:
        await update.message.reply_text(f"❌ {exc}", parse_mode="Markdown")
        return

    if not target.has_key:
        await update.message.reply_text(
            f"🔑 El target `{target.name}` no tiene claves configuradas.",
            parse_mode="Markdown",
        )
        return

    waiting = await update.message.reply_text(
        f"📡 Probando `{card.masked}` en `{target.name}`...",
        parse_mode="Markdown",
    )

    async def lookup(bin_number: str) -> BinInfo | None:
        try:
            info, _ = await bin_client.lookup(bin_number)
            return info
        except BinError:
            return None

    try:
        result = await check_stripe(
            card,
            target=target,
            bin_lookup=lookup,
            proxy=pool,
            timeout=timeout,
        )
        text = format_check(card, result, footer)
    except Exception:
        log.exception("Fallo inesperado en check de %s", card.masked)
        text = "⚠️ Error interno. Inténtalo más tarde."

    await waiting.edit_text(text, parse_mode="Markdown")


async def target_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    registry: TargetRegistry = context.bot_data["targets"]
    footer: str = context.bot_data["footer"]
    await update.message.reply_text(
        format_targets(registry, footer), parse_mode="Markdown"
    )


async def _lookup_bin(bin6: str) -> tuple[str, str]:
    """(bank, country) del BIN. Best-effort: si falla, devuelve N/A."""
    import inspect

    from . import binlist as bl

    try:
        from .config import load_config

        cfg = load_config(require_token=False)
    except Exception:
        cfg = None

    for name in ("fetch_bin", "get_bin", "lookup_bin", "lookup", "fetch"):
        fn = getattr(bl, name, None)
        if not callable(fn):
            continue
        try:
            res = fn(bin6, cfg) if cfg is not None else fn(bin6)
        except TypeError:
            res = fn(bin6)
        except Exception:
            continue
        if inspect.isawaitable(res):
            res = await res
        if isinstance(res, tuple):
            res = res[0]
        if res is not None:
            return (
                getattr(res, "bank", None) or "N/A",
                getattr(res, "country", None) or "N/A",
            )
    return "N/A", "N/A"


async def gen_cmd(update, context):
    """/gen <pan|mm|yy|cvv> — completa los 'x' con PANs Luhn-validos."""
    import random

    from .formatter import format_gen
    from .luhn import generate_pans

    args = list(getattr(context, "args", None) or [])
    if not args:
        await update.message.reply_text("Uso: /gen 416916141303xxxx|01|2029|xxx")
        return

    parts = args[0].split("|")
    pan_t = parts[0].strip()
    mm = parts[1].strip() if len(parts) > 1 else ""
    yy = parts[2].strip() if len(parts) > 2 else ""
    cvv_t = parts[3].strip() if len(parts) > 3 else ""

    if "x" not in pan_t.lower():
        await update.message.reply_text("La plantilla no trae 'x' que completar.")
        return

    n = 10
    if len(args) > 1 and args[1].isdigit():
        n = max(1, min(50, int(args[1])))

    cards = []
    for pan in generate_pans(pan_t, n):
        cvv = "".join(
            str(random.randint(0, 9)) if c.lower() == "x" else c for c in cvv_t
        )
        cards.append(f"{pan}|{mm}|{yy}|{cvv}")

    bin6 = pan_t[:6]
    bank, country = await _lookup_bin(bin6)
    await update.message.reply_text(
        format_gen(cards, bin6, bank, country), parse_mode=None
    )
