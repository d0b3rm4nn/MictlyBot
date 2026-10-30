"""Handlers de Telegram."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from . import proxy as proxy_mod
from .bincheck import (
    BinCheckClient,
    BinError,
    BinNotFound,
    BinRateLimited,
    normalize_bin,
)
from .cardcheck import CardData, RateLimited, make_bin_lookup
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
    limiter: RateLimiter = context.bot_data["rate_limiter"]
    allowed, retry_after = limiter.allow(update.effective_user.id)
    if not allowed:
        await update.message.reply_text(
            f"⏳ Vas muy rápido. Espera {retry_after:.0f} s e inténtalo de nuevo."
        )
        return

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
    client: BinCheckClient = context.bot_data["bin_client"]
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
        f"📡 Consultando en **BinCheck** para: `{bin_number}`...",
        parse_mode="Markdown",
    )

    try:
        info, from_cache = await client.lookup(bin_number)
        text = format_bin(info, from_cache, footer)
    except BinRateLimited as exc:
        text = _mensaje_429(exc)
    except BinNotFound as exc:
        text = f"❌ {exc}"
    except BinError as exc:
        text = f"⚠️ {exc}"
    except Exception:
        log.exception("Fallo inesperado en lookup de %s", bin_number)
        text = "⚠️ Error interno. Inténtalo más tarde."

    await waiting.edit_text(text, parse_mode="Markdown")


def _mensaje_429(exc: BinRateLimited) -> str:
    """Mensaje del /bin cuando BinCheck responde 429, con la cola de reintento."""
    cola = f" — reintenta en {exc.retry_after:g} s" if exc.retry_after else ""
    return f"⚠️ **Límite de API:** {exc}{cola}"


async def check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    limiter: RateLimiter = context.bot_data["check_limiter"]
    registry: TargetRegistry = context.bot_data["targets"]
    bin_client: BinCheckClient = context.bot_data["bin_client"]
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

    try:
        result = await check_stripe(
            card,
            target=target,
            bin_lookup=make_bin_lookup(bin_client),
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


def _bin_prefix(template: str) -> str | None:
    """Primeros 6 dígitos de la plantilla, aunque haya 'x' de por medio."""
    first6 = template[:6]
    if "x" not in first6.lower():
        return first6
    digits = "".join(c for c in template if c.isdigit())
    return digits[:6] if len(digits) >= 6 else None


async def _lookup_bin(context: ContextTypes.DEFAULT_TYPE, bin6: str) -> tuple[str, str]:
    """(bank, country) del BIN. Best-effort: si falla, devuelve N/A."""
    client: BinCheckClient = context.bot_data["bin_client"]
    lookup = make_bin_lookup(client)
    try:
        info = await lookup(bin6)
    except (BinError, ValueError):
        return "n/d [err]", "n/d [err]"
    if isinstance(info, RateLimited):
        retry = info.retry_after
        tag = f"n/d [429/{retry:g}s]" if retry else "n/d [429]"
        return tag, tag
    if info is None:
        return "n/d [404]", "n/d [404]"
    return info.bank or "N/A", info.country or "N/A"


async def gen_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/gen <pan|mm|yy|cvv> [n] — completa los 'x' con PANs Luhn-validos."""
    limiter: RateLimiter = context.bot_data["rate_limiter"]
    allowed, retry_after = limiter.allow(update.effective_user.id)
    if not allowed:
        await update.message.reply_text(
            f"⏳ Vas muy rápido. Espera {retry_after:.0f} s e inténtalo de nuevo."
        )
        return

    import random

    from .formatter import format_gen
    from .luhn import generate_pans
    from .scheme import cvv_length, pan_length

    args = list(getattr(context, "args", None) or [])
    if not args:
        await update.message.reply_text(
            "Uso: `/gen 416916141303xxxx|01|2029|xxx [n]`\n"
            "_También acepta solo el BIN (`/gen 416916`) y lo completa solo._",
            parse_mode="Markdown",
        )
        return

    parts = args[0].split("|")
    pan_t = parts[0].strip()
    mm = parts[1].strip() if len(parts) > 1 else ""
    yy = parts[2].strip() if len(parts) > 2 else ""
    cvv_t = parts[3].strip() if len(parts) > 3 else ""

    if not pan_t:
        await update.message.reply_text("Falta el PAN en la plantilla.")
        return

    has_x = "x" in pan_t.lower()

    # Largo y CVV segun esquema: Amex 15/4, Diners 14/3, resto 16/3.
    target = pan_length(pan_t)
    if len(pan_t) < target:  # p. ej. solo el BIN -> se rellena solo
        pan_t = pan_t + "x" * (target - len(pan_t))
        has_x = True
    elif len(pan_t) > target and set(pan_t[target:].lower()) <= {"x"}:
        # Sobraban 'x': recortamos al largo del esquema. Si al recortar se queda
        # sin 'x', el ultimo digito pasa a 'x' para que el control se recalcule
        # con la longitud nueva (antes no era el control de un PAN mas corto).
        pan_t = pan_t[:target]
        if "x" not in pan_t:
            pan_t = pan_t[:-1] + "x"
        has_x = True

    n = 10 if has_x else 1
    if len(args) > 1 and args[1].isdigit():
        n = max(1, min(50, int(args[1])))

    # CVV: si el usuario mando todo 'x' y el esquema pide otro ancho, se ajusta.
    if cvv_t and set(cvv_t.lower()) == {"x"} and len(cvv_t) != cvv_length(pan_t):
        cvv_t = "x" * cvv_length(pan_t)

    cards = []
    for pan in generate_pans(pan_t, n):
        cvv = "".join(
            str(random.randint(0, 9)) if c.lower() == "x" else c for c in cvv_t
        )
        cards.append(f"{pan}|{mm}|{yy}|{cvv}")

    if not has_x:
        cards = cards[:1]

    bin6 = _bin_prefix(pan_t)
    bank, country = await _lookup_bin(context, bin6) if bin6 else ("N/A", "N/A")
    await update.message.reply_text(
        format_gen(cards, bin6 or pan_t[:6], bank, country), parse_mode=None
    )
