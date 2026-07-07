import hashlib

from pit_panel.web.routes.debug import _file_checksum


def test_file_checksum_success(tmp_path):
    test_file = tmp_path / "test_file.txt"
    test_file.write_bytes(b"test data")

    expected_hash = hashlib.sha256(b"test data").hexdigest()

    assert _file_checksum(str(test_file)) == expected_hash


def test_file_checksum_large_file(tmp_path):
    # Test reading a file larger than the 4096 chunk size
    test_file = tmp_path / "large_file.txt"
    data = b"a" * 10000
    test_file.write_bytes(data)

    expected_hash = hashlib.sha256(data).hexdigest()
    assert _file_checksum(str(test_file)) == expected_hash


def test_file_checksum_missing_file():
    # Attempting to read a file that doesn't exist should return empty string
    assert _file_checksum("/non/existent/path/file.txt") == ""


def test_file_checksum_empty_file(tmp_path):
    test_file = tmp_path / "empty_file.txt"
    test_file.write_bytes(b"")

    expected_hash = hashlib.sha256(b"").hexdigest()
    assert _file_checksum(str(test_file)) == expected_hash
