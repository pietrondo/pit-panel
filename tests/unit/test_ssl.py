from pit_panel.web.routes.ssl import CaddyfileConfig, _generate_caddyfile, _sanitize


def test_sanitize_removes_dangerous_characters():
    assert _sanitize('test"test') == "testtest"
    assert _sanitize("test\ntest") == "testtest"
    assert _sanitize("test\rtest") == "testtest"
    assert _sanitize("test{test}") == "testtest"
    assert _sanitize('a\nb\rc"d{e}f') == "abcdef"
    assert _sanitize("") == ""


def test_generate_caddyfile_prevents_injection():
    malicious_email = "admin@a.com\nmalicious_directive"
    caddyfile = _generate_caddyfile(
        CaddyfileConfig(
            email=malicious_email,
            domain="example.com",
            panel_sub="panel",
            dns_provider="cloudflare",
        )
    )
    assert "admin@a.commalicious_directive" in caddyfile
    assert "\nmalicious_directive" not in caddyfile

    malicious_eab = 'key"\nother_directive {'
    caddyfile2 = _generate_caddyfile(
        CaddyfileConfig(
            email="admin@a.com",
            domain="example.com",
            panel_sub="panel",
            dns_provider="",
            acme_provider="zerossl",
            eab_key_id=malicious_eab,
            eab_hmac="hmac",
        )
    )
    assert "\n" not in _sanitize(malicious_eab)
    assert 'eab "keyother_directive " "hmac"' in caddyfile2


def test_sanitize_removes_backslashes():
    assert _sanitize("test\\test") == "testtest"
    assert _sanitize("test\rtest") == "testtest"
    assert _sanitize("test\ntest") == "testtest"
    assert _sanitize('a\\b\\c"d{e}f`') == "abcdef"
