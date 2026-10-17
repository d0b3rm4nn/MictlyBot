"""Formato de la respuesta para Telegram (Markdown)."""

from __future__ import annotations

import re

from .binlist import BinInfo
from .cardcheck import CardData, CheckResult
from .targets import Target

# Markdown rompe con nombres de banco que traen _ * [ ] —
_MD_SPECIALS = re.compile(r"([_*\[\]()`])")

_ICONS = {"success": "✅", "info": "⚠️", "danger": "❌", "unknown": "❓", "dead": "🔑"}


def _safe(text: str) -> str:
    return _MD_SPECIALS.sub(r"\\\1", text)


def format_bin(info: BinInfo, from_cache: bool, footer: str) -> str:
    lines = [
        "✅ **Resultado BinList**",
        f"💳 **BIN:** `{info.bin_number}`",
        f"🏦 **Banco:** {_safe(info.bank)}",
        f"🌍 **País:** {_safe(info.country)} {info.emoji}",
        f"📝 **Marca:** {_safe(info.label)}",
        f"💳 **Tipo:** {_safe(info.card_type)}",
    ]
    if info.prepaid:
        lines.append("🎫 **Prepaga:** Sí")
    if from_cache:
        lines.append("\n⚡ _Resultado servido desde caché local._")
    return "\n".join(lines) + footer


def format_check(card: CardData, result: CheckResult, footer: str) -> str:
    icon = _ICONS.get(result.kind, "❓")
    lines = [
        f"{icon} **{_safe(result.label)}**",
        f"💳 `{card.masked}`",
    ]
    if result.bank or result.country:
        lines.append(f"🏦 {_safe(result.bank or 'N/A')} {result.emoji}")
        lines.append(f"🌍 {_safe(result.country or 'N/A')} · {_safe(result.card_type or 'N/A')}")
    if result.prepaid:
        lines.append("🎫 **Prepaga:** Sí")
    meta = f"⏱ {result.ms} ms · 🎯 `{result.target}`"
    if result.attempts > 1:
        meta += f" · {result.attempts} intentos"
    lines.append(f"\n_{meta}_")
    return "\n".join(lines) + footer


def format_targets(registry, footer: str) -> str:
    names = registry.names()
    if not names:
        return (
            "🎯 No hay `targets.toml`.\n"
            "Se usará el perfil de respaldo del `.env`." + footer
        )
    lines = ["🎯 **Perfiles configurados**", ""]
    for name in names:
        try:
            target: Target = registry.get(name)
        except Exception:
            continue
        lines.append(
            f"• `{name}` — {_safe(target.mode)} · `{_safe(target.masked_key())}`"
        )
    lines.append("")
    lines.append(f"_Por defecto: `{registry.default_name()}`_")
    return "\n".join(lines) + footer
