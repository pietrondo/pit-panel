from pit_panel.web.routes.ssl import CaddyfileConfig, _generate_caddyfile, _sanitize


def test_caddyfile_injection() -> None:
    import pytest

    malicious_email = "admin@localhost\n}\nmalicious_host {\nreverse_proxy 1.2.3.4\n}"

    config = CaddyfileConfig(
        email=malicious_email,
        domain="example.com",
        panel_sub="panel",
        dns_provider="cloudflare",
    )
    with pytest.raises(ValueError, match="Invalid characters in input"):
        _generate_caddyfile(config)


def test_caddyfile_injection_eab() -> None:
    import pytest

    malicious_key = 'key"\n}\nmalicious_host {\n"'

    config = CaddyfileConfig(
        email="admin@example.com",
        domain="example.com",
        panel_sub="panel",
        acme_provider="zerossl",
        eab_key_id=malicious_key,
        eab_hmac="hmac",
    )
    with pytest.raises(ValueError, match="Invalid characters in input"):
        _generate_caddyfile(config)


def test_sanitize() -> None:
    import pytest

    with pytest.raises(ValueError, match="Invalid characters in input"):
        _sanitize('a\nb\r\nc"d{e}f')
    assert _sanitize(None) == ""  # type: ignore[arg-type]
    assert _sanitize("") == ""
