from pit_panel.web.routes.ssl import CaddyfileConfig, _generate_caddyfile, _sanitize


def test_caddyfile_injection():
    # Attempting to inject newlines
    malicious_email = "admin@localhost\n}\nmalicious_host {\nreverse_proxy 1.2.3.4\n}"

    config = CaddyfileConfig(
        email=malicious_email,
        domain="example.com",
        panel_sub="panel",
        dns_provider="cloudflare",  # force generating the block with email
    )
    result = _generate_caddyfile(config)

    # We should not find the unescaped malicious configuration
    assert "malicious_host {" not in result
    # The email should have newlines and braces removed
    assert "admin@localhostmalicious_host" in result


def test_caddyfile_injection_eab():
    malicious_key = 'key"\n}\nmalicious_host {\n"'

    config = CaddyfileConfig(
        email="admin@example.com",
        domain="example.com",
        panel_sub="panel",
        acme_provider="zerossl",
        eab_key_id=malicious_key,
        eab_hmac="hmac",
    )
    result = _generate_caddyfile(config)

    assert "malicious_host {" not in result
    assert "malicious_host" in result


def test_sanitize():
    assert _sanitize('a\nb\r\nc"d{e}f') == "abcdef"
    assert _sanitize(None) == ""
    assert _sanitize("") == ""
