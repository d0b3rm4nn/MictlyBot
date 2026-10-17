"""Configuración leída desde el entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:
        return False

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    """Falta configuración obligatoria para arrancar."""


@dataclass(frozen=True)
class Config:
    token: str
    cache_ttl_seconds: int
    rate_limit_per_minute: int
    user_agent: str
    footer: str
    cache_db_path: str

    # --- checker de tarjetas ---
    targets_file: str = "targets.toml"
    default_target: str = ""
    check_rate_limit_per_minute: int = 3
    http_timeout: float = 30.0
    use_proxy: bool = True
    proxy_file: str = "proxy.txt"
    cardcheck_bin_cache: bool = True

    # respaldo si targets.toml no existe
    stripe_endpoint: str = "https://api.stripe.com/v1/payment_methods"
    stripe_key: str = ""
    stripe_origin: str = "https://js.stripe.com"
    stripe_referer: str = "https://js.stripe.com/"

    # solo para tools/stripe_probe.py
    stripe_secret_key: str = ""


def resolve_path(path: str) -> Path:
    """Ruta relativa al cwd si existe ahí; si no, a la raíz del proyecto."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    if candidate.exists():
        return candidate
    return ROOT / candidate


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if not raw:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def load_config(*, require_token: bool = True) -> Config:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    if require_token and not token:
        raise ConfigError(
            "TELEGRAM_TOKEN no está definido. Copia .env.example a .env y pega "
            "el token de @BotFather, o expón la variable en el entorno."
        )
    return Config(
        token=token,
        cache_ttl_seconds=_env_int("CACHE_TTL_SECONDS", 86400),
        rate_limit_per_minute=_env_int("RATE_LIMIT_PER_MINUTE", 5),
        user_agent=os.getenv("BINLIST_USER_AGENT", "MictlyBot/1.0").strip(),
        footer=os.getenv("FOOTER", "\n\n🤖 **Bot By d0b3rm4nn**").strip(),
        cache_db_path=os.getenv("CACHE_DB_PATH", "bins_cache.db").strip(),
        targets_file=os.getenv("TARGETS_FILE", "targets.toml").strip(),
        default_target=os.getenv("DEFAULT_TARGET", "").strip(),
        check_rate_limit_per_minute=_env_int("CHECK_RATE_LIMIT_PER_MINUTE", 3),
        http_timeout=_env_float("HTTP_TIMEOUT", 30.0),
        use_proxy=_env_bool("USE_PROXY", True),
        proxy_file=os.getenv("PROXY_FILE", "proxy.txt").strip(),
        cardcheck_bin_cache=_env_bool("CARDCHECK_BIN_CACHE", True),
        stripe_endpoint=os.getenv(
            "STRIPE_ENDPOINT", "https://api.stripe.com/v1/payment_methods"
        ).strip(),
        stripe_key=(os.getenv("STRIPE_KEY") or os.getenv("STRIPE_PK") or "").strip(),
        stripe_origin=os.getenv("STRIPE_ORIGIN", "https://js.stripe.com").strip(),
        stripe_referer=os.getenv("STRIPE_REFERER", "https://js.stripe.com/").strip(),
        stripe_secret_key=os.getenv("STRIPE_SECRET_KEY", "").strip(),
    )
