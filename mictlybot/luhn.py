"""Validación del dígito de control (algoritmo de Luhn).

Sirve para detectar números mal tecleados en formularios de pago. No genera,
no completa ni almacena números: recibe el valor, devuelve un booleano y
descarta la entrada.
"""

from __future__ import annotations

MIN_LENGTH = 12
MAX_LENGTH = 19


def strip_spaces(raw: str) -> str:
    return (raw or "").replace(" ", "").replace("-", "")


def passes_luhn(digits: str) -> bool:
    """True si el dígito de control es correcto."""
    if not digits.isdigit():
        return False
    total = 0
    # El último dígito es el de control; se recorre de derecha a izquierda.
    for index, char in enumerate(reversed(digits[:-1])):
        value = int(char)
        if index % 2 == 0:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return (total + int(digits[-1])) % 10 == 0


def check_card(raw: str) -> tuple[bool, str]:
    """Devuelve (valido, motivo_si_invalido)."""
    digits = strip_spaces(raw)
    if not digits:
        return False, "No enviaste ningún número."
    if not digits.isdigit():
        return False, "El número debe contener solo dígitos."
    if not MIN_LENGTH <= len(digits) <= MAX_LENGTH:
        return (
            False,
            f"La longitud debe estar entre {MIN_LENGTH} y {MAX_LENGTH} dígitos "
            f"(recibiste {len(digits)}).",
        )
    if not passes_luhn(digits):
        return False, "Dígito de control incorrecto."
    return True, ""
