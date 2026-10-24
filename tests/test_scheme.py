"""Largo por esquema y relleno automatico del BIN en /gen."""

import asyncio

from mictlybot.bincheck import BinError
from mictlybot.handlers import gen_cmd
from mictlybot.luhn import generate_pans, passes_luhn
from mictlybot.ratelimit import RateLimiter
from mictlybot.scheme import cvv_length, pan_length


def test_longitud_por_esquema():
    assert pan_length("37828224631000x") == 15   # Amex
    assert pan_length("36227212345678xx") == 14  # Diners
    assert pan_length("416916141303xxxx") == 16  # Visa
    assert pan_length("5555555555554444") == 16  # Mastercard


def test_cvv_por_esquema():
    assert cvv_length("37828224631000x") == 4
    assert cvv_length("416916") == 3


def test_generate_pans_honra_n_con_pocas_x():
    pans = generate_pans("37828224631000x", 3)
    assert len(pans) == 3
    assert all(passes_luhn(p) for p in pans)


class _Msg:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, **_kw):
        self.sent.append(text)


class _Update:
    def __init__(self):
        self.message = _Msg()
        self.effective_user = type("U", (), {"id": 1})()


class _Client:
    async def lookup(self, _bin):
        raise BinError("offline")


class _Ctx:
    def __init__(self, args):
        self.bot_data = {"rate_limiter": RateLimiter(100), "bin_client": _Client()}
        self.args = args


def _cards(out):
    return [ln for ln in out.splitlines() if "|" in ln]


def test_gen_solo_bin_rellena_a_16():
    u, c = _Update(), _Ctx(["416916"])
    asyncio.run(gen_cmd(u, c))
    cards = _cards(u.message.sent[-1])
    assert cards, "no salio ninguna tarjeta"
    assert all(len(k.split("|")[0]) == 16 for k in cards)
    assert all(passes_luhn(k.split("|")[0]) for k in cards)


def test_gen_amex_sale_a_15_con_cvv_de_4():
    u, c = _Update(), _Ctx(["37828224631000x|01|2029|xxx"])
    asyncio.run(gen_cmd(u, c))
    cards = _cards(u.message.sent[-1])
    assert cards
    for k in cards:
        pan, _mm, _yy, cvv = k.split("|")
        assert len(pan) == 15
        assert len(cvv) == 4


def test_generate_pans_da_variedad_con_una_sola_x():
    pans = generate_pans("37828224631000x", 3)
    assert len(pans) == 3
    assert len(set(pans)) == 3
    assert all(len(p) == 15 and passes_luhn(p) for p in pans)


def test_gen_diners_recorta_a_14():
    u, c = _Update(), _Ctx(["36227212345678xx|01|2029|xxx"])
    asyncio.run(gen_cmd(u, c))
    cards = _cards(u.message.sent[-1])
    assert cards
    assert all(len(k.split("|")[0]) == 14 for k in cards)
    assert all(passes_luhn(k.split("|")[0]) for k in cards)
