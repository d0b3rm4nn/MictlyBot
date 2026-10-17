import pytest

from mictlybot.cardcheck import RULES, CardData, match_rules
from mictlybot.targets import Target


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4571736012345678|12|2028|123", ("4571736012345678", "12", "2028", "123")),
        ("4571736012345678|12/28|123", ("4571736012345678", "12", "2028", "123")),
        ("4571736012345678|1|28|12", ("4571736012345678", "01", "2028", "12")),
    ],
)
def test_parse(raw, expected):
    card = CardData.parse(raw)
    assert (card.number, card.month, card.year, card.cvc) == expected


@pytest.mark.parametrize(
    "raw", ["", "123", "4571736012345678|12|2028", "abc|12|2028|123"]
)
def test_parse_errors(raw):
    with pytest.raises(ValueError):
        CardData.parse(raw)


def test_masked():
    card = CardData.parse("4571736012345678|12|2028|123")
    assert card.masked == "457173****5678|12|2028|123"
    assert card.bin == "457173"


def test_match_marcador_del_target():
    target = Target(name="t", needles=("PAGO OK",))
    assert match_rules("...PAGO OK...", target) == ("success", "CVV MATCHED")


def test_match_desconocido():
    assert match_rules("blah", Target(name="t")) == ("unknown", "UNKNOWN ERROR")


def test_catchall_es_ultimo_recurso():
    class FakeTarget:
        needles: tuple[str, ...] = ()

    t = FakeTarget()
    assert match_rules('{"object": "payment_method"}', t) == ("info", "CCN LIVE")
    assert match_rules(
        '{"object": "payment_method", "cvc_check": "pass"}', t
    ) == ("success", "CVV MATCHED")
    assert match_rules(
        '{"object": "payment_method", "cvc_check": "fail"}', t
    ) == ("info", "CCN LIVE")
    assert match_rules('{"error": {"code": "insufficient_funds"}}', t) == (
        "info",
        "INSUFFICIENT FUNDS",
    )
    assert match_rules('{"object": "error"}', t) == ("unknown", "UNKNOWN ERROR")


def test_catchall_no_tapa_reglas_especificas():
    needles = [n for n, _, _ in RULES]
    catch = needles.index('"object": "payment_method"')
    for needle in (
        '"cvc_check": "pass"',
        '"cvc_check": "fail"',
        "known test card",
        "incorrect_cvc",
        "insufficient_funds",
        "expired_card",
        "processing_error",
    ):
        assert needles.index(needle) < catch, f"{needle!r} queda tapada por el catch-all"
    assert needles[-1] == "-1", "el ultimo recurso tiene que ser -1"


def test_reglas_sin_duplicados():
    needles = [n for n, _, _ in RULES]
    dups = {n for n in needles if needles.count(n) > 1}
    assert not dups, f"needles duplicadas: {dups}"


def test_kinds_y_etiquetas():
    permitidos = {"success", "info", "danger"}
    for needle, kind, label in RULES:
        assert kind in permitidos, f"kind invalido en {needle!r}: {kind}"
        assert label[:1] not in {"✅", "🟢", "❌", "❓", "🔑"}, f"emoji en {label!r}"


