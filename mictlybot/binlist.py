"""Cliente asíncrono para lookup.binlist.net.

BinList solo devuelve metadatos públicos de un prefijo (6-8 dígitos): banco,
marca, país, tipo y esquema. No hay datos de tarjetas ni cuenta que descartar.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import asdict, dataclass, fields
from typing import Any, Protocol

import httpx

BIN_PATTERN = re.compile(r"^\d{6,8}$")
BASE_URL = "https://lookup.binlist.net/{bin}"
TIMEOUT_SECONDS = 10.0
MAX_RETRIES = 3


class BinError(Exception):
    """Fallo consultando BinList."""


class BinNotFound(BinError):
    """El prefijo no existe o no está en la base de datos."""


class BinRateLimited(BinError):
    """BinList respondió 429."""


@dataclass(frozen=True)
class BinInfo:
    bin_number: str
    bank: str
    country: str
    country_code: str
    emoji: str
    scheme: str
    card_type: str
    brand: str
    prepaid: bool

    @property
    def label(self) -> str:
        parts = [p for p in (self.scheme, self.brand) if p and p != "N/A"]
        return " ".join(parts) or "N/A"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BinInfo:
        return cls(**{f.name: data[f.name] for f in fields(cls)})


def normalize_bin(raw: str) -> str:
    """Acepta el prefijo con espacios o guiones; recorta a 8 dígitos.

    Lanza ValueError si trae letras o si quedan menos de 6 dígitos.
    """
    cleaned = (raw or "").strip().replace("-", "").replace(" ", "")
    if not cleaned.isdigit():
        raise ValueError("El BIN solo puede contener dígitos.")
    digits = cleaned[:8]
    if not BIN_PATTERN.match(digits):
        raise ValueError("El BIN debe tener entre 6 y 8 dígitos.")
    return digits


class CacheBackend(Protocol):
    """Contrato mínimo queBinListClient necesita de una caché."""

    def get(self, key: str) -> Any: ...

    def set(self, key: str, value: Any) -> None: ...


class BinListClient:
    def __init__(
        self,
        cache: CacheBackend,
        user_agent: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._cache = cache
        self._user_agent = user_agent
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=TIMEOUT_SECONDS,
                headers={
                    "Accept-Version": "3",
                    "User-Agent": self._user_agent,
                },
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def lookup(self, bin_number: str) -> tuple[BinInfo, bool]:
        """Devuelve (info, from_cache)."""
        cached = self._cache.get(bin_number)
        if cached is not None:
            # La caché SQLite guarda un dict serializado, no el dataclass.
            info = cached if isinstance(cached, BinInfo) else BinInfo.from_dict(cached)
            return info, True

        info = await self._fetch(bin_number)
        self._cache.set(bin_number, info.as_dict())
        return info, False

    async def _fetch(self, bin_number: str) -> BinInfo:
        client = await self._get_client()
        last_error: BinError | None = None

        for attempt in range(MAX_RETRIES):
            try:
                response = await client.get(BASE_URL.format(bin=bin_number))
            except httpx.HTTPError as exc:
                last_error = BinError(f"Error de conexión: {exc}")
            else:
                if response.status_code == 200:
                    return _parse(bin_number, response.json())
                if response.status_code == 429:
                    raise BinRateLimited(
                        "BinList está limitando las consultas. Espera un minuto."
                    )
                if response.status_code == 404:
                    raise BinNotFound(f"No se encontró información para `{bin_number}`.")
                last_error = BinError(
                    f"BinList respondió HTTP {response.status_code}."
                )

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)

        raise last_error or BinError("Fallo desconocido consultando BinList.")


def _parse(bin_number: str, data: dict[str, Any]) -> BinInfo:
    bank = (data.get("bank") or {}).get("name") or "N/A"
    country = data.get("country") or {}
    return BinInfo(
        bin_number=bin_number,
        bank=bank,
        country=country.get("name") or "N/A",
        country_code=country.get("alpha2") or "",
        emoji=country.get("emoji") or "🌐",
        scheme=(data.get("scheme") or "N/A").upper(),
        card_type=(data.get("type") or "N/A").upper(),
        brand=data.get("brand") or "",
        prepaid=bool(data.get("prepaid", False)),
    )
