import pytest

from mictlybot.binlist import normalize_bin


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("123456", "123456"),
        ("12345678", "12345678"),
        ("123456789", "12345678"),
        (" 123456 ", "123456"),
        ("1234-56", "123456"),
    ],
)
def test_normalize_accepts_valid(raw, expected):
    assert normalize_bin(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "12345", "1234567890x", "/bin 12345"])
def test_normalize_rejects_invalid(raw):
    with pytest.raises(ValueError):
        normalize_bin(raw)
