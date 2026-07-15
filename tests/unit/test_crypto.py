import hashlib

from pit_panel.security.crypto import hash_token


def test_hash_token_known_value() -> None:
    # SHA-256 of "test_token"
    expected = hashlib.sha256(b"test_token").hexdigest()
    assert hash_token("test_token") == expected

def test_hash_token_empty_string() -> None:
    # SHA-256 of empty string
    expected = hashlib.sha256(b"").hexdigest()
    assert hash_token("") == expected

def test_hash_token_different_inputs() -> None:
    # Ensure different inputs yield different hashes
    hash1 = hash_token("token1")
    hash2 = hash_token("token2")
    assert hash1 != hash2

def test_hash_token_length() -> None:
    # SHA-256 hexdigest should always be 64 characters
    assert len(hash_token("any_token")) == 64
