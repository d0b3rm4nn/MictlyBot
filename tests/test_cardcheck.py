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


@pytest.mark.parametrize("raw", ["", "123", "4571736012345678|12|2028", "abc|12|2028|123"])
def test_parse_errors(raw):
    with pytest.raises(ValueError):
        CardData.parse(raw)


def test_masked():
    card = CardData.parse("4571736012345678|12|2028|123")
    assert card.masked == "457173****5678|12|2028|123"
    assert card.bin == "457173"


def test_orden_de_reglas():
    needles = [n for n, _, _ in RULES]
    assert needles[0] == '"cvc_check": "pass"'
    assert needles.index("Thank You For Donation.") < needles.index("Thank You.")
    assert needles[-1] == "-1"


def test_reglas_sin_duplicados():
    needles = [n for n, _, _ in RULES]
    assert len(needles) == len(set(needles))


def test_match_marcador_del_target():
    target = Target(name="t", needles=("PAGO OK",))
    assert match_rules("...PAGO OK...", target) == ("success", "CVV MATCHED")


def test_match_desconocido():
    assert match_rules("blah", Target(name="t")) == ("unknown", "UNKNOWN ERROR")
