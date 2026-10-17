"""Perfiles de target: endpoint + claves + origin/referer + reglas propias.

Los perfiles viven en targets.toml, así cambiar de sitio no toca código.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from .config import Config, resolve_path

Auth = Literal["bearer", "basic", "key", "none"]
Mode = Literal["stripe", "form"]

DEFAULT_ENDPOINT = "https://api.stripe.com/v1/payment_methods"

STRIPE_FIELDS: dict[str, str] = {
    "type": "type",
    "number": "card[number]",
    "exp_month": "card[exp_month]",
    "exp_year": "card[exp_year]",
    "cvc": "card[cvc]",
    "name": "billing_details[name]",
    "line1": "billing_details[address][line1]",
    "city": "billing_details[address][city]",
    "state": "billing_details[address][state]",
    "zip": "billing_details[address][postal_code]",
    "country": "billing_details[address][country]",
}

DEAD_KEY_MARKERS: tuple[str, ...] = (
    "api_key_expired",
    "Invalid API Key",
    "Expired API Key",
    "Invalid API Key provided",
)


class TargetError(Exception):
    """Perfil inexistente o mal formado."""


@dataclass(slots=True)
class KeyRing:
    """Claves con rotación y descarte de las revocadas."""

    keys: list[str] = field(default_factory=list)
    _index: int = 0
    _dead: set[str] = field(default_factory=set)

    def current(self) -> str | None:
        alive = [k for k in self.keys if k and k not in self._dead]
        if not alive:
            return None
        return alive[self._index % len(alive)]

    def mark_dead(self, key: str) -> None:
        if key:
            self._dead.add(key)

    def rotate(self) -> bool:
        alive = [k for k in self.keys if k and k not in self._dead]
        if len(alive) < 2:
            return False
        self._index += 1
        return True

    @property
    def alive(self) -> int:
        return len([k for k in self.keys if k and k not in self._dead])


@dataclass(slots=True, frozen=True)
class Target:
    name: str
    mode: Mode = "stripe"
    endpoint: str = DEFAULT_ENDPOINT
    keys: tuple[str, ...] = ()
    auth: Auth = "bearer"
    origin: str = "https://js.stripe.com"
    referer: str = "https://js.stripe.com/"
    fields: dict[str, str] = field(default_factory=lambda: dict(STRIPE_FIELDS))
    extra: dict[str, str] = field(default_factory=dict)
    needles: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return self.keys[0] if self.keys else ""

    @property
    def has_key(self) -> bool:
        return bool(self.key)

    @property
    def is_live(self) -> bool:
        return any("_live_" in k for k in self.keys)

    def masked_key(self) -> str:
        if not self.key:
            return "(sin clave)"
        if len(self.key) <= 20:
            return self.key
        return f"{self.key[:12]}...{self.key[-4:]}"


class TargetRegistry:
    """Carga targets.toml y resuelve perfiles por nombre."""

    def __init__(
        self,
        path: str,
        *,
        default_name: str = "",
        fallback: Target | None = None,
    ) -> None:
        self._path: Path = resolve_path(path)
        self._default = default_name
        self._fallback = fallback
        self._lock = threading.Lock()
        self._mtime = 0.0
        self._data: dict = {}

    def _raw(self) -> dict:
        if not self._path.exists():
            return {}
        mtime = self._path.stat().st_mtime
        with self._lock:
            if mtime == self._mtime:
                return self._data
            with self._path.open("rb") as handle:
                self._data = tomllib.load(handle)
            self._mtime = mtime
            return self._data

    def names(self) -> list[str]:
        return sorted((self._raw().get("targets") or {}).keys())

    def default_name(self) -> str:
        return self._raw().get("default") or self._default or "default"

    def get(self, name: str | None = None) -> Target:
        data = self._raw()
        targets = data.get("targets") or {}
        chosen = name or self.default_name()

        if not targets:
            if self._fallback is None:
                raise TargetError("No hay targets.toml ni perfil de respaldo.")
            return self._fallback

        raw = targets.get(chosen)
        if raw is None:
            raise TargetError(
                f"Target desconocido: {chosen}. "
                f"Disponibles: {', '.join(self.names())}"
            )

        fields = dict(STRIPE_FIELDS)
        fields.update(raw.get("field_map") or {})

        keys = raw.get("keys")
        if keys is None:
            single = raw.get("key")
            keys = [single] if single else []

        return Target(
            name=chosen,
            mode=raw.get("mode", "stripe"),
            endpoint=raw.get("endpoint", DEFAULT_ENDPOINT),
            keys=tuple(k for k in keys if k),
            auth=raw.get("auth", "bearer"),
            origin=raw.get("origin", "https://js.stripe.com"),
            referer=raw.get("referer", "https://js.stripe.com/"),
            fields=fields,
            extra=dict(raw.get("extra") or {}),
            needles=tuple(raw.get("needles") or ()),
        )

    def get_or_none(self, name: str | None) -> Target | None:
        try:
            return self.get(name)
        except TargetError:
            return None

    @staticmethod
    def from_config(config: Config) -> TargetRegistry:
        fallback = Target(
            name="env",
            endpoint=config.stripe_endpoint,
            keys=tuple(k for k in (config.stripe_key,) if k),
            auth="key" if config.stripe_key.startswith("pk_") else "bearer",
            origin=config.stripe_origin,
            referer=config.stripe_referer,
        )
        return TargetRegistry(
            config.targets_file,
            default_name=config.default_target,
            fallback=fallback,
        )
