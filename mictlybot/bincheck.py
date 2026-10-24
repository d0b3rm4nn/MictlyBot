"""Cliente asincrono para la API de BinCheck.io (reemplaza a binlist.net).

Endpoint:  GET https://bincheck.io/api/bin/{bin}
Auth:      Authorization: Bearer $BINCHECK_API_KEY
Docs:      https://bincheck.io/docs
"""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from typing import Any, Protocol

import httpx

BIN_PATTERN = re.compile(r"^\d{6,8}$")
BASE_URL = "https://bincheck.io/api/bin/{bin}"
TIMEOUT_SECONDS = 10.0
MAX_RETRIES = 3
RETRY_STATUSES = frozenset({500, 502, 503, 504})
NOT_FOUND_MARK = "__not_found__"
SMALL_WORDS = frozenset({"of", "and", "the", "de", "del", "la", "el", "y"})


class BinError(Exception):
    """Fallo consultando BinCheck."""


class BinNotFound(BinError):
    """El prefijo no existe en la base de datos (404)."""


class BinAuthError(BinError):
    """Clave ausente, rechazada o sin plan para el endpoint (401/403/405)."""


class BinRateLimited(BinError):
    """BinCheck respondio 429."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


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
    """Acepta el prefijo con espacios o guiones; recorta a 8 digitos."""
    cleaned = (raw or "").strip().replace("-", "").replace(" ", "")
    if not cleaned.isdigit():
        raise ValueError("El BIN solo puede contener digitos.")
    digits = cleaned[:8]
    if not BIN_PATTERN.match(digits):
        raise ValueError("El BIN debe tener entre 6 y 8 digitos.")
    return digits


def flag_emoji(alpha2: str) -> str:
    """Emoji de bandera a partir del codigo ISO alpha-2."""
    code = (alpha2 or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return "🌐"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)


def pretty_country(name: str) -> str:
    """MEXICO -> Mexico; respeta palabras menores y siglas."""
    if not name or name == "N/A":
        return "N/A"
    out: list[str] = []
    for i, word in enumerate(name.split()):
        bare = word.strip("()").lower()
        out.append(bare if i and bare in SMALL_WORDS else word.capitalize())
    return " ".join(out)


class CacheBackend(Protocol):
    def get(self, key: str) -> Any: ...

    def set(self, key: str, value: Any) -> None: ...


class BinCheckClient:
    def __init__(
        self,
        cache: CacheBackend,
        user_agent: str,
        client: httpx.AsyncClient | None = None,
        proxy_provider: Callable[[], str | None] | None = None,
        api_key: str | None = None,
    ) -> None:
        self._cache = cache
        self._user_agent = user_agent
        self._client = client
        self._owns_client = client is None
        self._proxy_provider = proxy_provider
        self._api_key = (api_key or "").strip() or None

    def _key(self) -> str:
        key = self._api_key or os.environ.get("BINCHECK_API_KEY", "").strip()
        if not key:
            raise BinAuthError(
                "Falta BINCHECK_API_KEY. Ponla en el .env: BINCHECK_API_KEY=tu_clave"
            )
        return key

    def _headers(self) -> dict[str, str]:
        key = self._key()
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {key}",
            "x-api-key": key,
            "User-Agent": self._user_agent,
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=TIMEOUT_SECONDS, headers=self._headers()
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def _request(self, bin_number: str) -> httpx.Response:
        # Con rotacion de proxy hace falta un cliente por peticion; si nos
        # inyectaron un cliente (tests) o no hay proxy, reutilizamos el nuestro.
        if self._client is None and self._proxy_provider is not None:
            proxy_url = self._proxy_provider()
            async with httpx.AsyncClient(
                timeout=TIMEOUT_SECONDS, headers=self._headers(), proxy=proxy_url
            ) as client:
                return await client.get(BASE_URL.format(bin=bin_number))
        client = await self._get_client()
        return await client.get(BASE_URL.format(bin=bin_number))

    async def lookup(self, bin_number: str) -> tuple[BinInfo, bool]:
        """Devuelve (info, from_cache). Los 404 tambien se cachean."""
        cached = self._cache.get(bin_number)
        if cached is not None:
            if isinstance(cached, dict) and cached.get(NOT_FOUND_MARK):
                raise BinNotFound(
                    f"No se encontro informacion para `{bin_number}` (cache)."
                )
            info = cached if isinstance(cached, BinInfo) else BinInfo.from_dict(cached)
            return info, True

        try:
            info = await self._fetch(bin_number)
        except BinNotFound:
            self._cache.set(bin_number, {NOT_FOUND_MARK: True})
            raise

        self._cache.set(bin_number, info.as_dict())
        return info, False

    async def _fetch(self, bin_number: str) -> BinInfo:
        last_error: BinError | None = None

        for attempt in range(MAX_RETRIES):
            try:
                response = await self._request(bin_number)
            except httpx.HTTPError as exc:
                last_error = BinError(f"Error de conexión: {exc}")
            else:
                status = response.status_code

                if status == 200:
                    data = _json(response)
                    if data.get("success") is False:
                        code = data.get("code")
                        if code == 404:
                            raise BinNotFound(
                                _message(response)
                                or f"No se encontro informacion para `{bin_number}`."
                            )
                        raise BinError(
                            _message(response) or f"BinCheck respondio codigo {code}."
                        )
                    return _parse(bin_number, data)

                if status == 404:
                    raise BinNotFound(
                        _message(response)
                        or f"No se encontro informacion para `{bin_number}`."
                    )

                if status == 429:
                    hdr = (response.headers.get("Retry-After") or "").strip()
                    retry = float(hdr) if hdr.replace(".", "", 1).isdigit() else None
                    raise BinRateLimited(
                        "BinCheck esta limitando las consultas. Espera un poco.",
                        retry_after=retry,
                    )

                if status in (401, 403, 405):
                    raise BinAuthError(
                        _message(response)
                        or f"Clave rechazada por BinCheck (HTTP {status}). "
                        "Revisa BINCHECK_API_KEY y el plan de tu cuenta."
                    )

                last_error = BinError(
                    _message(response) or f"BinCheck respondio HTTP {status}."
                )

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt)

        raise last_error or BinError("Fallo desconocido consultando BinCheck.")


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _message(response: httpx.Response) -> str:
    data = _json(response)
    for key in ("message", "reason", "result", "error"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _parse(bin_number: str, data: dict[str, Any]) -> BinInfo:
    block = data.get("BIN") if isinstance(data.get("BIN"), dict) else data
    country = block.get("country") or {}
    alpha2 = (country.get("alpha2") or "").upper()

    if "issuer" in block:
        # Formato bincheck: brand es el esquema, level es el nivel de tarjeta.
        issuer = block.get("issuer") or {}
        scheme = block.get("brand") or "N/A"
        brand = block.get("level") or ""
    else:
        # Formato plano de binlist.net: scheme es el esquema y brand la submarca.
        issuer = block.get("bank") or {}
        scheme = block.get("scheme") or "N/A"
        brand = block.get("brand") or ""

    return BinInfo(
        bin_number=str(block.get("bin") or bin_number),
        bank=issuer.get("name") or "N/A",
        country=pretty_country(country.get("name") or "N/A"),
        country_code=alpha2,
        emoji=flag_emoji(alpha2),
        scheme=scheme.upper(),
        card_type=(block.get("type") or "N/A").upper(),
        brand=brand,
        prepaid=bool(block.get("prepaid", False)),
    )
