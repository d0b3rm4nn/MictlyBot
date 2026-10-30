import json

from mictlybot.otp.detect import find_challenge


def test_sin_next_action_devuelve_none():
    assert find_challenge(200, json.dumps({"object": "payment_method"})) is None


def test_redirect():
    raw = json.dumps({"next_action": {"redirect_to_url": {"url": "https://acs/x"}}})
    challenge = find_challenge(402, raw)
    assert challenge.kind == "redirect"
    assert challenge.acs_url == "https://acs/x"


def test_sdk_2():
    raw = json.dumps(
        {"next_action": {"use_stripe_sdk": {"three_d_secure_2_source": "tdsrc_1"}}}
    )
    challenge = find_challenge(402, raw)
    assert "3d_secure_2/hosted" in challenge.acs_url


def test_402_sin_action_no_es_challenge():
    assert find_challenge(402, '{"error": {"code": "authentication_required"}}') is None
