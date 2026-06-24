class TestPasswordHashing:
    def test_hash_and_verify(self, settings):
        from pit_panel.security.crypto import hash_password, verify_password

        pw = "my-secure-password"
        hashed = hash_password(pw, settings)
        assert hashed != pw
        assert verify_password(pw, hashed)
        assert not verify_password("wrong", hashed)

    def test_hash_is_unique(self, settings):
        from pit_panel.security.crypto import hash_password

        h1 = hash_password("pw", settings)
        h2 = hash_password("pw", settings)
        assert h1 != h2

    def test_token_hashing(self):
        from pit_panel.security.crypto import hash_token

        t = hash_token("abc123")
        assert len(t) == 64
        assert hash_token("abc123") == hash_token("abc123")
        assert hash_token("xyz") != hash_token("abc123")

    def test_encrypt_decrypt(self, settings):
        from pit_panel.security.crypto import decrypt_value, encrypt_value

        plain = "my sensitive data"
        enc = encrypt_value(plain, settings)
        assert enc != plain
        assert decrypt_value(enc, settings) == plain

    def test_fernet_key_generation(self, settings):
        from pit_panel.security.crypto import get_fernet

        f = get_fernet(settings)
        assert f is not None
