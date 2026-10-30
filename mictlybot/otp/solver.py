"""Resuelve el challenge en un Chromium real con perfil persistente."""

from __future__ import annotations

import asyncio
import hashlib
import time
from contextlib import suppress
from pathlib import Path

from .models import Challenge, OtpOutcome, OtpSource
from .parsers import find_otp_input, submit

CHALLENGE_HOSTS = ("hooks.stripe.com", "3d_secure")
DONE_TEXT = (
    "authentication complete",
    "authentication completed",
    "autenticación correcta",
    "authentication successful",
    "verified successfully",
    "completado",
    "success",
    "gracias",
)
FAIL_TEXT = ("código incorrecto", "incorrect", "inválido", "expirado", "expired")


def profile_for(root: Path, card_number: str) -> Path:
    digest = hashlib.sha1(card_number.encode()).hexdigest()[:16]
    return root / digest


async def _wait_verdict(page, deadline: float) -> OtpOutcome:
    while time.monotonic() < deadline:
        url = page.url
        if not any(marker in url for marker in CHALLENGE_HOSTS):
            return OtpOutcome("authenticated", "redirigido fuera del ACS", url)
        try:
            body = (await page.inner_text("body")).lower()
        except Exception:
            body = ""
        if any(marker in body for marker in FAIL_TEXT):
            return OtpOutcome("failed", "el ACS rechazó el código", url)
        if any(marker in body for marker in DONE_TEXT):
            return OtpOutcome("authenticated", "el ACS confirmó", url)
        await asyncio.sleep(0.5)
    return OtpOutcome("timeout", "sin veredicto del ACS", page.url)


async def solve(
    challenge: Challenge,
    *,
    source: OtpSource,
    profile_dir: Path,
    proxy_url: str | None,
    headless: bool = True,
    user_agent: str,
    platform: str = "Linux",
    locale: str = "es-MX",
    timezone_id: str = "America/Mexico_City",
    form_timeout: float = 25.0,
    otp_timeout: float = 120.0,
    verdict_timeout: float = 60.0,
    attempts: int = 2,
) -> OtpOutcome:
    from playwright.async_api import async_playwright

    profile_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            user_agent=user_agent,
            locale=locale,
            timezone_id=timezone_id,
            viewport={"width": 1366, "height": 768},
            proxy={"server": proxy_url} if proxy_url else None,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(
                challenge.acs_url, wait_until="domcontentloaded", timeout=45_000
            )

            for attempt in range(attempts):
                frame, locator = await find_otp_input(page, form_timeout)
                if frame is None:
                    if attempt == 0:
                        return await _wait_verdict(
                            page, time.monotonic() + min(verdict_timeout, 20)
                        )
                    return OtpOutcome("no_form", "no encontré input de OTP", page.url)

                code = await source.wait(otp_timeout)
                if code is None:
                    return OtpOutcome("timeout", "sin OTP en el plazo", page.url)

                await locator.fill(code)
                await submit(frame, locator)
                verdict = await _wait_verdict(page, time.monotonic() + verdict_timeout)
                if verdict.ok or verdict.kind == "timeout":
                    return verdict
            return OtpOutcome("failed", "se agotaron los intentos", page.url)
        finally:
            with suppress(Exception):
                await context.close()
