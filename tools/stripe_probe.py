"""Sonda de Stripe en modo TEST (sandbox). Solo PaymentMethods de prueba.

Explora los namespaces /v1 y /v2, distintas `Stripe-Version` y el catálogo de
PaymentMethods de prueba de Stripe, mostrando `status`, `decline_code` y errores.

No envía números de tarjeta crudos (Stripe lo bloquea en cuentas nuevas) ni usa
claves `sk_live_`: exige una clave `sk_test_`.

Uso:
    export STRIPE_SECRET_KEY=sk_test_...
    python tools/stripe_probe.py
    python tools/stripe_probe.py --versions
    python tools/stripe_probe.py --v2
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import httpx
from dotenv import load_dotenv

API = "https://api.stripe.com"

# PaymentMethods de prueba oficiales de Stripe (sandbox, no cuentas reales).
TEST_PAYMENT_METHODS: tuple[tuple[str, str, str], ...] = (
    ("visa_ok", "pm_card_visa", "aprobada"),
    ("visa_generic_decline", "pm_card_visa_chargeDeclined", "generic_decline"),
    (
        "visa_insufficient_funds",
        "pm_card_visa_chargeDeclinedInsufficientFunds",
        "insufficient_funds",
    ),
    ("visa_lost_card", "pm_card_visa_chargeDeclinedLostCard", "lost_card"),
    (
        "visa_velocity_exceeded",
        "pm_card_visa_chargeDeclinedVelocityLimitExceeded",
        "card_velocity_exceeded",
    ),
    ("visa_3ds_required", "pm_card_threeDSecure2Required", "requires_action"),
    ("mastercard_ok", "pm_card_mastercard", "aprobada"),
)

# Versiones de API con las que podemos comparar el header Stripe-Version.
SAMPLE_VERSIONS: tuple[str, ...] = (
    "2024-09-30.acacia",
    "2025-12-15.clover",
    "2026-01-28.preview",
)


def _fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_key() -> str:
    load_dotenv()
    key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if not key:
        _fail(
            "Falta STRIPE_SECRET_KEY. Cópiala del Dashboard (modo test) y "
            "ponla en .env: STRIPE_SECRET_KEY=sk_test_..."
        )
    if not key.startswith("sk_test_"):
        _fail(
            "La clave debe empezar por sk_test_. Por seguridad la sonda se "
            "niega a usar claves live o restringidas."
        )
    return key


def _auth_headers(key: str, version: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {key}"}
    if version:
        headers["Stripe-Version"] = version
    return headers


def _print_result(label: str, response: httpx.Response) -> None:
    print(f"\n=== {label} ===")
    print(f"HTTP {response.status_code}")
    try:
        data: Any = response.json()
    except ValueError:
        print(response.text)
        return
    error = data.get("error") if isinstance(data, dict) else None
    if error:
        print(
            "error.type={} code={} decline_code={}".format(
                error.get("type"),
                error.get("code"),
                error.get("decline_code"),
            )
        )
        print(f"message: {error.get('message')}")
        return
    if isinstance(data, dict):
        print(f"status: {data.get('status')}")
        if data.get("decline_code"):
            print(f"decline_code: {data.get('decline_code')}")
        if data.get("next_action"):
            print(f"next_action.type: {data['next_action'].get('type')}")
        print(f"id: {data.get('id')}")


def confirm_payment(
    client: httpx.Client,
    key: str,
    payment_method: str,
    version: str | None = None,
) -> httpx.Response:
    return client.post(
        f"{API}/v1/payment_intents",
        headers=_auth_headers(key, version),
        data={
            "amount": "1000",
            "currency": "usd",
            "payment_method": payment_method,
            "confirm": "true",
            "automatic_payment_methods[enabled]": "true",
            "automatic_payment_methods[allow_redirects]": "never",
        },
    )


def run_payment_methods(client: httpx.Client, key: str) -> None:
    print("\n########## /v1 · PaymentIntents (sandbox) ##########")
    for name, payment_method, expected in TEST_PAYMENT_METHODS:
        response = confirm_payment(client, key, payment_method)
        _print_result(f"{name} · {payment_method} ({expected})", response)


def run_versions(client: httpx.Client, key: str) -> None:
    print("\n########## /v1 · comparativa Stripe-Version ##########")
    for version in SAMPLE_VERSIONS:
        response = confirm_payment(client, key, "pm_card_visa", version=version)
        _print_result(f"Stripe-Version: {version}", response)


def run_v2(client: httpx.Client, key: str) -> None:
    print("\n########## /v2 · namespace nuevo ##########")
    # /v2 exige el header Stripe-Version. Listamos event_destinations.
    response = client.get(
        f"{API}/v2/core/event_destinations",
        headers=_auth_headers(key, SAMPLE_VERSIONS[1]),
    )
    _print_result("GET /v2/core/event_destinations", response)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sonda de Stripe en modo test")
    parser.add_argument(
        "--versions", action="store_true", help="compara headers Stripe-Version"
    )
    parser.add_argument("--v2", action="store_true", help="prueba el namespace /v2")
    parser.add_argument("--all", action="store_true", help="ejecuta todo")
    args = parser.parse_args()

    key = load_key()
    run_all = args.all or not (args.versions or args.v2)

    with httpx.Client(timeout=30.0) as client:
        if run_all:
            run_payment_methods(client, key)
        if args.all or args.versions:
            run_versions(client, key)
        if args.all or args.v2:
            run_v2(client, key)

    print("\nListo. Todo lo anterior es simulado (test mode).")


if __name__ == "__main__":
    main()
