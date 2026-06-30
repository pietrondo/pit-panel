"""Tests for WordPress proxy module."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from pit_panel.core.wp_proxy import (
    _fix_cookie_path,
    _fix_location,
    _rewrite_content,
    _rewrite_urls,
    read_env,
)


def test_read_env(tmp_path):
    app_dir = tmp_path / "blog"
    app_dir.mkdir()
    env_file = app_dir / ".env"
    env_file.write_text("DB_NAME=appdb\nDB_PASSWORD=secret123\n")
    result = read_env(str(tmp_path), "blog")
    assert result == {"DB_NAME": "appdb", "DB_PASSWORD": "secret123"}


def test_read_env_missing(tmp_path):
    result = read_env(str(tmp_path), "blog")
    assert result == {}


def test_rewrite_urls_html():
    prefix = "/apps/3/wp"
    content = b"""
    <link href="/wp-admin/css/styles.css">
    <script src="/wp-includes/js/jquery.js"></script>
    <img src="/wp-content/themes/theme/img.png">
    """
    result = _rewrite_urls(content, prefix)
    assert b"/apps/3/wp/wp-admin/css/styles.css" in result
    assert b"/apps/3/wp/wp-includes/js/jquery.js" in result
    assert b"/apps/3/wp/wp-content/themes/theme/img.png" in result


def test_rewrite_urls_no_match():
    prefix = "/apps/3/wp"
    content = b"<a href='/some-other-path/'>"
    result = _rewrite_urls(content, prefix)
    assert result == content


def test_rewrite_content_html():
    prefix = "/apps/3/wp"
    content = b"<a href='/wp-admin/plugins.php'>"
    result = _rewrite_content(content, "text/html", prefix)
    assert b"/apps/3/wp/wp-admin/plugins.php" in result


def test_rewrite_content_css():
    prefix = "/apps/3/wp"
    content = b"background: url(/wp-content/themes/theme/bg.png);"
    result = _rewrite_content(content, "text/css", prefix)
    assert b"/apps/3/wp/wp-content/themes/theme/bg.png" in result


def test_rewrite_content_json():
    prefix = "/apps/3/wp"
    content = b'{"url": "/wp-admin/admin-ajax.php"}'
    result = _rewrite_content(content, "application/json", prefix)
    assert b"/apps/3/wp/wp-admin/admin-ajax.php" in result


def test_rewrite_content_binary():
    prefix = "/apps/3/wp"
    content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    result = _rewrite_content(content, "image/png", prefix)
    assert result == content


def test_fix_cookie_path_root():
    prefix = "/apps/3/wp"
    cookie = "wordpress_logged_in_abc=token; path=/; HttpOnly; Secure"
    result = _fix_cookie_path(cookie, prefix)
    assert "path=/apps/3/wp" in result
    assert "HttpOnly" in result
    assert "Secure" in result


def test_fix_cookie_path_wpadmin():
    prefix = "/apps/3/wp"
    cookie = "wordpress_sec_abc=token; path=/wp-admin; HttpOnly"
    result = _fix_cookie_path(cookie, prefix)
    assert "path=/apps/3/wp/wp-admin" in result


def test_fix_cookie_path_multi():
    prefix = "/apps/3/wp"
    cookie = "wordpress_logged_in_abc=token; path=/; HttpOnly; Secure"
    result = _fix_cookie_path(cookie, prefix)
    assert "path=/apps/3/wp" in result
    assert "HttpOnly" in result
    assert "Secure" in result


def test_fix_location_root_relative():
    prefix = "/apps/3/wp"
    result = _fix_location("/wp-admin/", prefix)
    assert result == "/apps/3/wp/wp-admin/"


def test_fix_location_already_prefixed():
    prefix = "/apps/3/wp"
    result = _fix_location("/apps/3/wp/wp-admin/", prefix)
    assert result == "/apps/3/wp/wp-admin/"


def test_fix_location_absolute():
    prefix = "/apps/3/wp"
    result = _fix_location("https://blog.example.com/wp-admin/", prefix)
    assert result == "https://blog.example.com/wp-admin/"


@pytest.mark.asyncio
async def test_auto_login_returns_none_on_missing_password(tmp_path):
    from pit_panel.core.wp_proxy import auto_login
    app_dir = tmp_path / "blog"
    app_dir.mkdir()
    (app_dir / ".env").write_text("WP_ADMIN_USER=admin\n")
    result = await auto_login(str(tmp_path), "blog", 8081, "blog.example.com")
    assert result is None


@pytest.mark.asyncio
async def test_auto_login_subprocess_fails(tmp_path):
    from pit_panel.core.wp_proxy import auto_login

    app_dir = tmp_path / "blog"
    app_dir.mkdir()
    (app_dir / ".env").write_text(
        "WP_ADMIN_USER=admin\nWP_ADMIN_PASSWORD=secret\n"
    )

    with patch("pit_panel.core.wp_proxy.asyncio.create_subprocess_exec") as mock_sub:
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(b"", b"error: container not found"))
        proc.returncode = 1
        mock_sub.return_value = proc

        result = await auto_login(str(tmp_path), "blog", 8081, "blog.example.com")
    assert result is None


@pytest.mark.asyncio
async def test_auto_login_returns_none_on_no_cookies(tmp_path):
    from pit_panel.core.wp_proxy import auto_login

    app_dir = tmp_path / "blog"
    app_dir.mkdir()
    (app_dir / ".env").write_text(
        "WP_ADMIN_USER=admin\nWP_ADMIN_PASSWORD=secret\n"
    )

    with patch("pit_panel.core.wp_proxy.asyncio.create_subprocess_exec") as mock_sub:
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(json.dumps({"cookies": [], "redirect_to": "/wp-admin/"}).encode(), b""))  # noqa: E501
        proc.returncode = 0
        mock_sub.return_value = proc

        result = await auto_login(str(tmp_path), "blog", 8081, "blog.example.com")
    assert result is None


def test_auto_login_php_code_uses_arrow_syntax():
    """Verify PHP inline code uses => not : for array key-value pairs."""
    import inspect
    from pit_panel.core.wp_proxy import auto_login
    source = inspect.getsource(auto_login)
    assert '"cookies"=>' in source, "PHP array must use => not : for keys"
    assert '"cookies":' not in source, "Found JS-style ':' in PHP code - use => instead"


@pytest.mark.asyncio
async def test_auto_login_success(tmp_path):
    from pit_panel.core.wp_proxy import auto_login

    app_dir = tmp_path / "blog"
    app_dir.mkdir()
    (app_dir / ".env").write_text(
        "WP_ADMIN_USER=admin\nWP_ADMIN_PASSWORD=secret\n"
    )

    cookie_json = json.dumps({
        "cookies": [
            "wordpress_logged_in_abc=token; Path=/; HttpOnly",
            "wordpress_sec_abc=token; Path=/wp-admin; HttpOnly",
        ],
        "redirect_to": "/wp-admin/",
    })

    with patch("pit_panel.core.wp_proxy.asyncio.create_subprocess_exec") as mock_sub:
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(cookie_json.encode(), b""))
        proc.returncode = 0
        mock_sub.return_value = proc

        result = await auto_login(str(tmp_path), "blog", 8081, "blog.example.com")
    assert result is not None
    redirect_to, cookies = result
    assert redirect_to == "/wp-admin/"
    assert len(cookies) == 2
    assert any("wordpress_logged_in" in c for c in cookies)
    assert any("Path=/" in c for c in cookies)
