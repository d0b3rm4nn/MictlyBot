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
