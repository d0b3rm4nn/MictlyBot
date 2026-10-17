import textwrap

import pytest

from mictlybot.targets import KeyRing, TargetError, TargetRegistry


@pytest.fixture
def registry(tmp_path):
    path = tmp_path / "targets.toml"
    path.write_text(
        textwrap.dedent(
            """
            default = "uno"

            [targets.uno]
            auth = "bearer"
            keys = ["sk_live_AAA", "sk_live_BBB"]
            origin = "https://ejemplo.com"
            referer = "https://ejemplo.com/donar"

            [targets.dos]
            auth = "key"
            keys = ["pk_live_CCC"]
            """
        ),
        encoding="utf-8",
    )
    return TargetRegistry(str(path))


def test_names(registry):
    assert registry.names() == ["dos", "uno"]


def test_default(registry):
    target = registry.get()
    assert target.name == "uno"
    assert target.auth == "bearer"
    assert target.origin == "https://ejemplo.com"


def test_por_nombre(registry):
    assert registry.get("dos").auth == "key"


def test_desconocido(registry):
    with pytest.raises(TargetError):
        registry.get("nope")
    assert registry.get_or_none("nope") is None


def test_masked_key(registry):
    assert registry.get().masked_key().startswith("sk_live_AAA")


def test_rotacion_de_claves():
    ring = KeyRing(["a", "b"])
    assert ring.current() == "a"
    ring.mark_dead("a")
    assert ring.current() == "b"
    assert ring.alive == 1
    assert ring.rotate() is False


def test_sin_toml(tmp_path):
    reg = TargetRegistry(str(tmp_path / "nada.toml"))
    assert reg.names() == []
    with pytest.raises(TargetError):
        reg.get()
