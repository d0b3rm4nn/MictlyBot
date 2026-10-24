from mictlybot.bincheck import BinInfo
from mictlybot.formatter import _safe, format_bin

INFO = BinInfo(
    bin_number="123456",
    bank="Banco_de_Prueba",
    country="Colombia",
    country_code="CO",
    emoji="🇨🇴",
    scheme="VISA",
    card_type="DEBIT",
    brand="VISA",
    prepaid=False,
)

FOOTER = "\n\nfooter"


def test_safe_escapes_markdown():
    assert _safe("Banco_de_Prueba") == "Banco\\_de\\_Prueba"


def test_format_contains_all_fields():
    out = format_bin(INFO, from_cache=False, footer=FOOTER)
    assert "123456" in out
    assert "🇨🇴" in out
    assert "VISA" in out
    assert "DEBIT" in out
    assert "caché" not in out
    assert out.endswith(FOOTER)


def test_format_flags_prepaid_and_cache():
    out = format_bin(
        INFO.__class__(**{**INFO.__dict__, "prepaid": True}),
        from_cache=True,
        footer=FOOTER,
    )
    assert "Prepaga" in out
    assert "caché local" in out
