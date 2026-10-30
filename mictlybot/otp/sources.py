"""Fuentes automáticas de OTP."""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress

import httpx

FIVESIM = "https://5sim.net/v1"


class WebhookOtpSource:
    """Cola alimentada por una app Android que reenvía los SMS del banco."""

    def __init__(self, queue: asyncio.Queue[str]) -> None:
        self._queue = queue

    async def wait(self, timeout: float) -> str | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout)
        except asyncio.TimeoutError:
            return None


class FiveSimOtpSource:
    """Solo útil si el número de la tarjeta es uno que controlas."""

    def __init__(self, token: str, country: str = "mexico", product: str = "any") -> None:
        self._token = token
        self._country = country
        self._product = product
        self._order_id: int | None = None

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    async def wait(self, timeout: float) -> str | None:
        deadline = time.monotonic() + timeout
        async with httpx.AsyncClient(timeout=15.0) as client:
            path = f"/user/buy/activation/{self._country}/any/{self._product}"
            try:
                response = await client.get(f"{FIVESIM}{path}", headers=self._headers)
                response.raise_for_status()
                self._order_id = int(response.json()["id"])
            except (httpx.HTTPError, ValueError, KeyError):
                return None
            while time.monotonic() < deadline:
                with suppress(httpx.HTTPError, ValueError):
                    response = await client.get(
                        f"{FIVESIM}/user/check/{self._order_id}", headers=self._headers
                    )
                    sms = response.json().get("sms") or []
                    if sms:
                        return str(sms[-1]["code"])
                await asyncio.sleep(3.0)
            return None

    async def release(self, *, cancel: bool) -> None:
        if self._order_id is None:
            return
        verb = "cancel" if cancel else "finish"
        async with httpx.AsyncClient(timeout=10.0) as client:
            with suppress(httpx.HTTPError):
                await client.get(
                    f"{FIVESIM}/user/{verb}/{self._order_id}", headers=self._headers
                )
