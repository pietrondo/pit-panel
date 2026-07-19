"""Tests for the string utilities module."""

from pit_panel.core.string_utils import truncate_string


def test_truncate_string_short() -> None:
    """Test truncating a string shorter than the max length."""
    text = "Hello, world!"
    assert truncate_string(text, 50) == "Hello, world!"


def test_truncate_string_exact() -> None:
    """Test truncating a string exactly the max length."""
    text = "Hello, world!"
    assert truncate_string(text, 13) == "Hello, world!"


def test_truncate_string_long() -> None:
    """Test truncating a string longer than the max length."""
    text = "Hello, world!"
    assert truncate_string(text, 10) == "Hello, ..."


def test_truncate_string_very_short_max() -> None:
    """Test truncating a string with a max length less than 3."""
    text = "Hello, world!"
    assert truncate_string(text, 2) == ".."
    assert truncate_string(text, 1) == "."
    assert truncate_string(text, 0) == ""


def test_truncate_string_empty() -> None:
    """Test truncating an empty string."""
    assert truncate_string("", 50) == ""
