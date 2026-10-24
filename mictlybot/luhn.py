"""Validación del dígito de control (algoritmo de Luhn).

Sirve para detectar números mal tecleados en formularios de pago. No genera,
no completa ni almacena números: recibe el valor, devuelve un booleano y
descarta la entrada.
"""

from __future__ import annotations

import random

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


def luhn_valid(number: str) -> bool:
    """True si el numero cierra en Luhn (suma multiplo de 10)."""
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def check_digit(partial: str) -> str:
    """Digito que vuelve Luhn-valido a partial + <digito>."""
    total = 0
    for i, ch in enumerate(reversed(partial)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def generate_pans(template: str, n: int = 10) -> list[str]:
    """Completa los 'x' de la plantilla con PANs Luhn-validos.

    Si la plantilla no da para n combinaciones unicas (p. ej. solo el BIN con
    una 'x' final), randomiza tambien el ultimo digito fijo para dar variedad.
    """
    t = template.strip().lower()
    if not t:
        return []
    idxs = [i for i, c in enumerate(t) if c == "x"]
    if not idxs:
        return [t] * n
    last = len(t) - 1
    out: list[str] = []
    seen: set[str] = set()

    def _attempt(free: list[int]) -> str | None:
        chars = list(t)
        for i in free:
            chars[i] = str(random.randint(0, 9))
        partial = "".join(chars[:last])
        if t[last] == "x":
            chars[last] = check_digit(partial)
        elif check_digit(partial) != t[last]:
            return None
        return "".join(chars)

    free = [i for i in idxs if i != last]
    guard = 0
    while len(out) < n and guard < n * 200:
        guard += 1
        pan = _attempt(free)
        if pan and pan not in seen:
            seen.add(pan)
            out.append(pan)

    # Sin posiciones libres suficientes: randomizamos el digito anterior.
    if len(out) < n and last >= 1:
        alt = sorted({i for i in (*free, last - 1) if i >= 0})
        guard = 0
        while len(out) < n and guard < n * 200:
            guard += 1
            pan = _attempt(alt)
            if pan and pan not in seen:
                seen.add(pan)
                out.append(pan)

    if out and len(out) < n:  # ultimo recurso: repetir en ciclo
        base = list(out)
        i = 0
        while len(out) < n:
            out.append(base[i % len(base)])
            i += 1
    return out
