from pit_panel.web.routes.ssl import _generate_caddyfile, _sanitize


def test_sanitize_removes_dangerous_characters():
    assert _sanitize('test"test') == "testtest"
    assert _sanitize("test\ntest") == "testtest"
    assert _sanitize("test\rtest") == "testtest"
    assert _sanitize("test{test}") == "testtest"
    assert _sanitize('a\nb\rc"d{e}f') == "abcdef"
    assert _sanitize("") == ""


def test_generate_caddyfile_prevents_injection():
    # Test that newline injection is prevented
    malicious_email = "admin@a.com\nmalicious_directive"
    caddyfile = _generate_caddyfile(
        email=malicious_email,
        domain="example.com",
        panel_sub="panel",
        dns_provider="cloudflare",
        api_var="CF_API_TOKEN",
        acme_provider="letsencrypt",
        eab_key_id="",
        eab_hmac="",
    )
    # Since email block is generated, we check its content
    assert "admin@a.commalicious_directive" in caddyfile
    assert "\nmalicious_directive" not in caddyfile

    # Test that EAB key id injection is prevented
    malicious_eab = 'key"\nother_directive {'
    caddyfile2 = _generate_caddyfile(
        email="admin@a.com",
        domain="example.com",
        panel_sub="panel",
        dns_provider="",
        api_var="CF_API_TOKEN",
        acme_provider="zerossl",
        eab_key_id=malicious_eab,
        eab_hmac="hmac",
    )
    # The newlines, quotes, and braces should be stripped
    assert "\n" not in _sanitize(malicious_eab)
    assert 'eab "keyother_directive " "hmac"' in caddyfile2
