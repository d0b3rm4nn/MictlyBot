from mictlybot.luhn import check_digit, generate_pans, luhn_valid


def test_genera_luhn_validos():
    pans = generate_pans("416916141303xxxx", 10)
    assert len(pans) == 10
    assert len(set(pans)) == 10
    for p in pans:
        assert len(p) == 16
        assert p[:12] == "416916141303"
        assert luhn_valid(p)


def test_ultimo_digito_fijo():
    pans = generate_pans("416916141303xxx0", 5)
    for p in pans:
        assert p.endswith("0")
        assert luhn_valid(p)


def test_sin_x():
    assert generate_pans("4242424242424242", 3) == ["4242424242424242"] * 3


def test_check_digit_conocido():
    assert check_digit("416916141303386") == "0"
    assert luhn_valid("4169161413033860")
