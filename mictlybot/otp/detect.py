"""Extrae el challenge del payload de Stripe. Ningún 402 es un challenge."""

from __future__ import annotations

import json

from .models import Challenge

HOOKS = "https://hooks.stripe.com"


def find_challenge(status: int, raw: str) -> Challenge | None:
    if status not in (200, 402):
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None

    action = payload.get("next_action")
    if not isinstance(action, dict):
        return None

    redirect = action.get("redirect_to_url") or {}
    url = redirect.get("url")
    if url:
        return Challenge(
            kind="redirect",
            acs_url=url,
            return_url=redirect.get("return_url") or "",
        )

    sdk = action.get("use_stripe_sdk") or {}
    source = sdk.get("three_d_secure_2_source")
    if source:
        return Challenge(
            kind="sdk",
            acs_url=f"{HOOKS}/3d_secure_2/hosted?source={source}&livemode=true",
            source=source,
        )

    legacy = sdk.get("source")  # 3DS1 heredado
    if legacy:
        return Challenge(kind="redirect", acs_url=f"{HOOKS}/3d_secure_redirect/{legacy}")

    return None
