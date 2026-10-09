"""Configuración leída desde el entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:
        return False

load_dotenv()


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


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def load_config() -> Config:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    if not token:
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
    )
