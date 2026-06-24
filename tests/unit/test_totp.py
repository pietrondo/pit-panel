class TestTOTP:
    def test_generate_secret(self):
        from pit_panel.security.totp import generate_totp_secret

        secret = generate_totp_secret()
        assert len(secret) >= 16

    def test_secrets_are_unique(self):
        from pit_panel.security.totp import generate_totp_secret

        s1 = generate_totp_secret()
        s2 = generate_totp_secret()
        assert s1 != s2

    def test_get_totp_uri(self):
        from pit_panel.security.totp import generate_totp_secret, get_totp_uri

        secret = generate_totp_secret()
        uri = get_totp_uri(secret, "admin")
        assert "admin" in uri
        assert "pit-panel" in uri
        assert uri.startswith("otpauth://")

    def test_verify_valid_code(self):
        import pyotp
        from pit_panel.security.totp import verify_totp

        secret = pyotp.random_base32()
        code = pyotp.TOTP(secret).now()
        assert verify_totp(secret, code)

    def test_verify_invalid_code(self):
        from pit_panel.security.totp import generate_totp_secret, verify_totp

        secret = generate_totp_secret()
        assert not verify_totp(secret, "000000")
