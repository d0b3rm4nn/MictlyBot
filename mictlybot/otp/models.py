"""Modelos del flujo OTP. Dominio puro, sin Playwright."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class Challenge:
    kind: str  # "redirect" | "sdk"
    acs_url: str
    source: str = ""
    livemode: bool = True
    return_url: str = ""


@dataclass(slots=True)
class OtpOutcome:
    kind: str  # authenticated | frictionless | failed | timeout | no_form | error
    detail: str = ""
    final_url: str = ""

    @property
    def ok(self) -> bool:
        return self.kind in {"authenticated", "frictionless"}


class OtpSource(Protocol):
    async def wait(self, timeout: float) -> str | None: ...


class ManualOtpSource:
    """El código lo escribe el usuario en el chat."""

    def __init__(self, future: asyncio.Future[str]) -> None:
        self._future = future

    async def wait(self, timeout: float) -> str | None:
        try:
            return await asyncio.wait_for(asyncio.shield(self._future), timeout)
        except asyncio.TimeoutError:
            return None
