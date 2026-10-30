"""Heurísticas para encontrar el formulario del ACS. Cada emisor pinta el suyo."""

from __future__ import annotations

import asyncio
import time

OTP_SELECTORS = (
    "input[autocomplete='one-time-code']",
    "input[type='tel']",
    "input[inputmode='numeric']",
    "input[name*='otp' i]",
    "input[id*='otp' i]",
    "input[name*='code' i]",
    "input[maxlength='6']",
    "input[maxlength='4']",
    "input[type='number']",
    "input[type='text']",
)

SUBMIT_SELECTORS = (
    "button[type='submit']",
    "input[type='submit']",
    "button[id*='submit' i]",
    "button:has-text('Continuar')",
    "button:has-text('Enviar')",
    "button:has-text('Confirmar')",
    "button:has-text('Submit')",
    "button:has-text('Verify')",
    "button:has-text('Confirm')",
)


async def find_otp_input(page, timeout: float):
    """(frame, locator) del primer input visible, o (None, None)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for frame in page.frames:
            for selector in OTP_SELECTORS:
                try:
                    locator = frame.locator(selector).first
                    if await locator.count() and await locator.is_visible():
                        return frame, locator
                except Exception:
                    continue
        await asyncio.sleep(0.4)
    return None, None


async def submit(frame, locator) -> None:
    for selector in SUBMIT_SELECTORS:
        try:
            button = frame.locator(selector).first
            if await button.count() and await button.is_enabled():
                await button.click()
                return
        except Exception:
            continue
    await locator.press("Enter")
