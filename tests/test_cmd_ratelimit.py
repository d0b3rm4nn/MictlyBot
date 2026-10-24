"""/gen respeta el rate limit por usuario."""

import asyncio

from mictlybot.handlers import gen_cmd
from mictlybot.ratelimit import RateLimiter


class _Msg:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, **_kw):
        self.sent.append(text)


class _Update:
    def __init__(self):
        self.message = _Msg()
        self.effective_user = type("U", (), {"id": 7})()


class _Ctx:
    def __init__(self, limiter):
        self.bot_data = {"rate_limiter": limiter}
        self.args = []


def test_gen_segunda_llamada_bloquea():
    lim = RateLimiter(1)
    u, c = _Update(), _Ctx(lim)
    asyncio.run(gen_cmd(u, c))          # consume el único token
    asyncio.run(gen_cmd(u, c))          # debe rebotar
    assert "Vas muy rápido" in u.message.sent[-1]
