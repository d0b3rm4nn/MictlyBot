"""Formato de la respuesta para Telegram (Markdown)."""

from __future__ import annotations

import re

from .binlist import BinInfo

# Markdown rompe con nombres de banco que traen _ * [ ] —
_MD_SPECIALS = re.compile(r"([_*\[\]()`])")


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
