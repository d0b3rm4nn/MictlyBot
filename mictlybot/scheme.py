"""Largo de PAN y CVV segun el esquema de la tarjeta.

Tabla portada de namso-gen (MIT). Solo cubre los casos con largo distinto
de 16; el resto cae en el default.
"""

from __future__ import annotations

import re

_AMEX = re.compile(r"^3[47]")
_DINERS = re.compile(r"^3[0689]")
_DEFAULT_PAN = 16


def _digits_prefix(raw: str) -> str:
    """Digitos iniciales del patron, cortando en la primera 'x' o no-digito."""
    out: list[str] = []
    for ch in (raw or "").strip():
        if ch.isdigit():
            out.append(ch)
        else:
            break
    return "".join(out)


def pan_length(raw: str) -> int:
    """Largo esperado del PAN para el prefijo dado."""
    prefix = _digits_prefix(raw)
    if _AMEX.match(prefix):
        return 15
    if _DINERS.match(prefix):
        return 14
    return _DEFAULT_PAN


def cvv_length(raw: str) -> int:
    """Largo del CVV: 4 para Amex, 3 para el resto."""
    return 4 if _AMEX.match(_digits_prefix(raw)) else 3
