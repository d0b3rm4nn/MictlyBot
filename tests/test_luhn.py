import pytest

from mictlybot.luhn import MAX_LENGTH, MIN_LENGTH, check_card, passes_luhn, strip_spaces


def with_check_digit(prefix: str) -> str:
    """Completa un prefijo de test con el dígito que lo hace válido.

    Solo para construir fixtures de prueba; no se usa en el bot.
    """
    for candidate in range(10):
        if passes_luhn(prefix + str(candidate)):
            return prefix + str(candidate)
    raise AssertionError("ningún dígito de control sirve")


@pytest.mark.parametrize(
    "digits",
    ["4539578763621486", "6011000990139424", "4111111111111111"],
)
def test_valid_numbers(digits):
    assert passes_luhn(digits)
    valid, reason = check_card(digits)
    assert valid
    assert reason == ""


@pytest.mark.parametrize(
    "valid_number",
    ["4539578763621486", "6011000990139424", "4111111111111111"],
)
def test_invalid_check_digit(valid_number):
    wrong = valid_number[:-1] + str((int(valid_number[-1]) + 1) % 10)
    assert not passes_luhn(wrong)
    ok, reason = check_card(wrong)
    assert not ok
    assert reason == "Dígito de control incorrecto."


def test_strips_spaces_and_dashes():
    assert strip_spaces("4539 5787-6362 1486") == "4539578763621486"
    assert check_card("4539 5787 6362 1486")[0]


def test_single_digit_never_valid():
    assert not passes_luhn("4")


def test_empty_input():
    ok, reason = check_card("")
    assert not ok
    assert "No enviaste" in reason


def test_non_digits_rejected():
    ok, reason = check_card("45395787636214ab")
    assert not ok
    assert "solo dígitos" in reason


def test_too_short():
    ok, reason = check_card("4" * (MIN_LENGTH - 1))
    assert not ok
    assert "longitud" in reason


def test_too_long():
    ok, reason = check_card("4" * (MAX_LENGTH + 1))
    assert not ok
    assert "longitud" in reason


@pytest.mark.parametrize("length", [MIN_LENGTH, 13, 16, MAX_LENGTH])
def test_length_boundaries_accepted(length):
    number = with_check_digit("4" * (length - 1))
    assert len(number) == length
    assert check_card(number)[0] is True


def test_luhn_does_not_store_input():
    """El módulo no debe retener el número entre llamadas."""
    number = with_check_digit("9" * 15)
    assert check_card(number)[0]
    assert check_card("4" * 16)[0] is False
