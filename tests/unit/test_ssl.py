import unittest.mock as mock

import pytest

from pit_panel.web.routes.ssl import (
    CaddyfileConfig,
    SSLGenerateForm,
    _check_caddy_running,
    _check_port80,
    _generate_caddyfile,
    _get_acme_config,
    _get_tls_block,
    _sanitize,
    ssl_generate,
    ssl_renew,
    ssl_renew_all,
    ssl_setup,
)


def test_sanitize_removes_dangerous_characters() -> None:
    import pytest

    bad_inputs = [
        'test"test', "test\ntest", "test\rtest", "test{test}", 'a\nb\rc"d{e}f',
        "test test", "test\ttest", "test`test", "test\'test", "test;test",
        "test|test", "test&test"
    ]
    for bad in bad_inputs:
        with pytest.raises(ValueError, match="Invalid characters in input"):
            _sanitize(bad)
    assert _sanitize("") == ""
    assert _sanitize("valid.domain-name_123@abc=def") == "valid.domain-name_123@abc=def"


def test_generate_caddyfile_prevents_injection() -> None:
    import pytest

    malicious_email = "admin@a.com\nmalicious_directive"
    with pytest.raises(ValueError, match="Invalid characters in input"):
        _generate_caddyfile(
            CaddyfileConfig(
                email=malicious_email,
                domain="example.com",
                panel_sub="panel",
                dns_provider="cloudflare",
            )
        )

    malicious_eab = 'key"\nother_directive {'
    with pytest.raises(ValueError, match="Invalid characters in input"):
        _generate_caddyfile(
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


def test_sanitize_removes_backslashes() -> None:
    import pytest

    for bad in ["test\\test", "test\rtest", "test\ntest", 'a\\b\\c"d{e}f`']:
        with pytest.raises(ValueError, match="Invalid characters in input"):
            _sanitize(bad)


def test_get_acme_config() -> None:
    assert _get_acme_config("buypass", "", "") == "issuer buypass"
    assert _get_acme_config("google", "key", "hmac") == 'issuer google {eab "key" "hmac"}'
    assert _get_acme_config("unknown", "", "") == ""


def test_get_tls_block() -> None:
    assert _get_tls_block("", "", "") == ""


def test_ssl_generate_form_as_form() -> None:
    form = SSLGenerateForm.as_form(email="test@example.com")
    assert form.email == "test@example.com"


def test_generate_caddyfile_no_dns_no_acme_clause() -> None:

    config = CaddyfileConfig(
        email="test@example.com",
        domain="example.com",
        panel_sub="panel",
        dns_provider="",
        acme_provider="letsencrypt",
    )
    caddyfile = _generate_caddyfile(config)
    assert "panel.example.com {" in caddyfile


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@mock.patch("asyncio.create_subprocess_exec")
async def test_check_caddy_running(mock_run: mock.MagicMock) -> None:
    proc_mock = mock.AsyncMock()
    proc_mock.returncode = 0
    mock_run.return_value = proc_mock
    assert await _check_caddy_running() is True

    proc_mock = mock.AsyncMock()
    proc_mock.returncode = 1
    mock_run.return_value = proc_mock
    assert await _check_caddy_running() is False

    mock_run.side_effect = Exception("error")
    assert await _check_caddy_running() is False


@mock.patch("socket.socket")
def test_check_port80(mock_socket: mock.MagicMock) -> None:
    mock_s = mock.MagicMock()
    mock_socket.return_value = mock_s
    assert _check_port80() is True

    mock_s.bind.side_effect = OSError("error")
    assert _check_port80() is False


class MockRequest:
    def __init__(self, session: dict[str, str] | None = None) -> None:
        self.session = session or {}


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@mock.patch("pit_panel.web.routes.ssl.get_admin")
async def test_ssl_setup_no_user(mock_get_admin: mock.MagicMock) -> None:
    mock_get_admin.return_value = None
    req = MockRequest()
    db = mock.AsyncMock()
    resp = await ssl_setup(req, db)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@mock.patch("pit_panel.web.routes.ssl.get_admin")
async def test_ssl_generate_no_user(mock_get_admin: mock.MagicMock) -> None:
    mock_get_admin.return_value = None
    req = MockRequest()
    form = SSLGenerateForm()
    db = mock.AsyncMock()
    resp = await ssl_generate(req, form, db)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@mock.patch("pit_panel.web.routes.ssl.get_admin")
async def test_ssl_renew_no_user(mock_get_admin: mock.MagicMock) -> None:
    mock_get_admin.return_value = None
    req = MockRequest()
    db = mock.AsyncMock()
    resp = await ssl_renew(req, "test.com", db)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@mock.patch("pit_panel.web.routes.ssl.get_admin")
async def test_ssl_renew_invalid_domain(mock_get_admin: mock.MagicMock) -> None:
    mock_get_admin.return_value = mock.MagicMock()
    req = MockRequest()
    db = mock.AsyncMock()
    resp = await ssl_renew(req, "invalid domain", db)
    assert resp.status_code == 400


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@mock.patch("pit_panel.web.routes.ssl.get_admin")
async def test_ssl_renew_all_no_user(mock_get_admin: mock.MagicMock) -> None:
    mock_get_admin.return_value = None
    req = MockRequest()
    db = mock.AsyncMock()
    resp = await ssl_renew_all(req, db)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@mock.patch("pit_panel.web.routes.ssl.get_admin")
@mock.patch("pit_panel.web.routes.ssl.get_settings")
@mock.patch("pit_panel.web.routes.ssl.CaddyManager")
@mock.patch("pit_panel.web.routes.ssl._check_caddy_running")
@mock.patch("pit_panel.web.routes.ssl._check_port80")
@mock.patch("pit_panel.web.routes.ssl.Path")
@mock.patch("pit_panel.web.routes.ssl.render")
@mock.patch("pit_panel.web.routes.ssl.get_last_ssl_renew_check")
async def test_ssl_setup_with_user(
    mock_get_last_ssl_renew_check: mock.MagicMock,
    mock_render: mock.MagicMock,
    mock_path: mock.MagicMock,
    mock_check_port80: mock.MagicMock,
    mock_check_caddy: mock.MagicMock,
    mock_caddy_manager_class: mock.MagicMock,
    mock_get_settings: mock.MagicMock,
    mock_get_admin: mock.MagicMock,
) -> None:
    mock_get_admin.return_value = mock.MagicMock()
    mock_settings = mock.MagicMock()
    mock_get_settings.return_value = mock_settings

    mock_caddy_manager = mock.MagicMock()
    mock_caddy_manager.get_certificates = mock.AsyncMock(return_value=[])
    mock_caddy_manager.generate_and_reload = mock.AsyncMock(return_value="Success")
    mock_caddy_manager.renew_certificate = mock.AsyncMock()
    mock_caddy_manager.save_api_token.return_value = " - Token saved"
    mock_caddy_manager_class.return_value = mock_caddy_manager

    mock_check_caddy.return_value = True
    mock_check_port80.return_value = True

    mock_path_instance = mock.MagicMock()
    mock_path_instance.exists.return_value = True
    mock_path_instance.read_text.return_value = "existing_caddyfile"
    mock_path.return_value = mock_path_instance

    mock_render.return_value = "rendered html"

    db_result = mock.MagicMock()
    db_result.scalars.return_value.all.return_value = []
    db = mock.AsyncMock()
    db.execute.return_value = db_result

    req = MockRequest()

    resp = await ssl_setup(req, db)

    assert resp == "rendered html"
    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["caddy_running"] is True
    assert kwargs["port80_free"] is True
    assert kwargs["current_caddyfile"] == "existing_caddyfile"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@mock.patch("pit_panel.web.routes.ssl.get_admin")
@mock.patch("pit_panel.web.routes.ssl.get_settings")
@mock.patch("pit_panel.web.routes.ssl.CaddyManager")
@mock.patch("pit_panel.web.routes.ssl._check_caddy_running")
@mock.patch("pit_panel.web.routes.ssl._check_port80")
@mock.patch("pit_panel.web.routes.ssl.render")
@mock.patch("pit_panel.web.routes.ssl.get_last_ssl_renew_check")
async def test_ssl_generate_with_user(
    mock_get_last_ssl_renew_check: mock.MagicMock,
    mock_render: mock.MagicMock,
    mock_check_port80: mock.MagicMock,
    mock_check_caddy: mock.MagicMock,
    mock_caddy_manager_class: mock.MagicMock,
    mock_get_settings: mock.MagicMock,
    mock_get_admin: mock.MagicMock,
) -> None:
    mock_get_admin.return_value = mock.MagicMock()
    mock_settings = mock.MagicMock()
    mock_settings.effective_domain = "example.com"
    mock_settings.panel_subdomain = "panel"
    mock_get_settings.return_value = mock_settings

    mock_caddy_manager = mock.MagicMock()
    mock_caddy_manager.get_certificates = mock.AsyncMock(return_value=[])
    mock_caddy_manager.generate_and_reload = mock.AsyncMock(return_value="Success")
    mock_caddy_manager.renew_certificate = mock.AsyncMock()
    mock_caddy_manager.save_api_token.return_value = " - Token saved"
    mock_caddy_manager_class.return_value = mock_caddy_manager

    mock_check_caddy.return_value = True
    mock_check_port80.return_value = True

    mock_render.return_value = "rendered html"

    db_result = mock.MagicMock()
    db_result.scalars.return_value.all.return_value = []
    db = mock.AsyncMock()
    db.execute.return_value = db_result

    req = MockRequest()
    form = SSLGenerateForm(
        email="test@example.com",
        acme_provider="letsencrypt",
        dns_provider="cloudflare",
        api_var="CF_API_TOKEN",
        api_token="mytoken",
        eab_key_id="",
        eab_hmac="",
    )

    resp = await ssl_generate(req, form, db)

    assert resp == "rendered html"
    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["caddy_result"] == "Success - Token saved"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@mock.patch("pit_panel.web.routes.ssl.get_admin")
@mock.patch("pit_panel.web.routes.ssl.get_settings")
@mock.patch("pit_panel.web.routes.ssl.CaddyManager")
@mock.patch("pit_panel.web.routes.ssl.AppManager")
@mock.patch("pit_panel.web.routes.ssl._check_caddy_running")
@mock.patch("pit_panel.web.routes.ssl._check_port80")
@mock.patch("pit_panel.web.routes.ssl.Path")
@mock.patch("pit_panel.web.routes.ssl.render")
@mock.patch("pit_panel.web.routes.ssl.get_last_ssl_renew_check")
async def test_ssl_renew_with_user(
    mock_get_last_ssl_renew_check: mock.MagicMock,
    mock_render: mock.MagicMock,
    mock_path: mock.MagicMock,
    mock_check_port80: mock.MagicMock,
    mock_check_caddy: mock.MagicMock,
    mock_app_manager_class: mock.MagicMock,
    mock_caddy_manager_class: mock.MagicMock,
    mock_get_settings: mock.MagicMock,
    mock_get_admin: mock.MagicMock,
) -> None:
    mock_get_admin.return_value = mock.MagicMock()
    mock_settings = mock.MagicMock()
    mock_settings.base_domain = "example.com"
    mock_get_settings.return_value = mock_settings

    mock_caddy_manager = mock.MagicMock()
    mock_caddy_manager.get_certificates = mock.AsyncMock(return_value=[])
    mock_caddy_manager.renew_certificate = mock.AsyncMock(return_value="Renewed")
    mock_caddy_manager.add_subdomain = mock.AsyncMock()
    mock_caddy_manager_class.return_value = mock_caddy_manager

    mock_app_manager = mock.MagicMock()
    mock_app_manager.get_template_info.return_value = {"default_port": 8080}
    mock_app_manager_class.return_value = mock_app_manager

    mock_check_caddy.return_value = True
    mock_check_port80.return_value = True

    mock_path_instance = mock.MagicMock()
    mock_path_instance.exists.return_value = True
    mock_path_instance.read_text.return_value = "existing_caddyfile"
    mock_path.return_value = mock_path_instance

    mock_render.return_value = "rendered html"

    db_result = mock.MagicMock()
    mock_sd = mock.MagicMock()
    mock_sd.app_type = "some_app"
    db_result.scalar_one_or_none.return_value = mock_sd

    db_result2 = mock.MagicMock()
    db_result2.scalars.return_value.all.return_value = []

    db = mock.AsyncMock()
    db.execute.side_effect = [db_result, db_result2]

    req = MockRequest()

    resp = await ssl_renew(req, "test.example.com", db)

    assert resp == "rendered html"
    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["renew_result"] == "Renewed"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@mock.patch("pit_panel.web.routes.ssl.get_admin")
@mock.patch("pit_panel.web.routes.ssl.get_settings")
@mock.patch("pit_panel.web.routes.ssl.CaddyManager")
@mock.patch("pit_panel.web.routes.ssl.AppManager")
@mock.patch("pit_panel.web.routes.ssl._check_caddy_running")
@mock.patch("pit_panel.web.routes.ssl._check_port80")
@mock.patch("pit_panel.web.routes.ssl.Path")
@mock.patch("pit_panel.web.routes.ssl.render")
@mock.patch("pit_panel.web.routes.ssl.get_last_ssl_renew_check")
async def test_ssl_renew_all_with_user(
    mock_get_last_ssl_renew_check: mock.MagicMock,
    mock_render: mock.MagicMock,
    mock_path: mock.MagicMock,
    mock_check_port80: mock.MagicMock,
    mock_check_caddy: mock.MagicMock,
    mock_app_manager_class: mock.MagicMock,
    mock_caddy_manager_class: mock.MagicMock,
    mock_get_settings: mock.MagicMock,
    mock_get_admin: mock.MagicMock,
) -> None:
    mock_get_admin.return_value = mock.MagicMock()
    mock_settings = mock.MagicMock()
    mock_settings.base_domain = "example.com"
    mock_settings.effective_domain = "panel.example.com"
    mock_get_settings.return_value = mock_settings

    mock_caddy_manager = mock.MagicMock()
    mock_caddy_manager.get_certificates = mock.AsyncMock(return_value=[])
    mock_caddy_manager.renew_certificate = mock.AsyncMock()

    async def add_subdomain_side_effect(subdomain: str, base: str, port: int = 80) -> None:
        if subdomain == "fail":
            raise Exception("Failed")

    mock_caddy_manager.add_subdomain = mock.AsyncMock(side_effect=add_subdomain_side_effect)
    mock_caddy_manager_class.return_value = mock_caddy_manager

    mock_app_manager = mock.MagicMock()
    mock_app_manager.get_template_info.return_value = {"default_port": 8080}
    mock_app_manager_class.return_value = mock_app_manager

    mock_check_caddy.return_value = True
    mock_check_port80.return_value = True

    mock_path_instance = mock.MagicMock()
    mock_path_instance.exists.return_value = True
    mock_path_instance.read_text.return_value = "existing_caddyfile"
    mock_path.return_value = mock_path_instance

    mock_render.return_value = "rendered html"

    db_result = mock.MagicMock()
    mock_sd1 = mock.MagicMock()
    mock_sd1.app_type = "app1"
    mock_sd1.subdomain = "ok"
    mock_sd1.base_domain = "example.com"

    mock_sd2 = mock.MagicMock()
    mock_sd2.app_type = "app2"
    mock_sd2.subdomain = "fail"
    mock_sd2.base_domain = "example.com"

    db_result.scalars.return_value.all.return_value = [mock_sd1, mock_sd2]

    db_result2 = mock.MagicMock()
    db_result2.scalars.return_value.all.return_value = []

    db = mock.AsyncMock()
    db.execute.side_effect = [db_result, db_result2]

    req = MockRequest()

    resp = await ssl_renew_all(req, db)

    assert resp == "rendered html"
    mock_render.assert_called_once()
    kwargs = mock_render.call_args[1]
    assert kwargs["renew_result"] == {"success": True, "ok": 1, "fail": 1}
    mock_caddy_manager.renew_certificate.assert_called_once_with("panel.example.com")


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@mock.patch("pit_panel.web.routes.ssl.get_admin")
@mock.patch("pit_panel.web.routes.ssl.get_settings")
@mock.patch("pit_panel.web.routes.ssl.CaddyManager")
@mock.patch("pit_panel.web.routes.ssl.AppManager")
@mock.patch("pit_panel.web.routes.ssl._check_caddy_running")
@mock.patch("pit_panel.web.routes.ssl._check_port80")
@mock.patch("pit_panel.web.routes.ssl.Path")
@mock.patch("pit_panel.web.routes.ssl.render")
@mock.patch("pit_panel.web.routes.ssl.get_last_ssl_renew_check")
async def test_ssl_renew_exception(
    mock_get_last_ssl_renew_check: mock.MagicMock,
    mock_render: mock.MagicMock,
    mock_path: mock.MagicMock,
    mock_check_port80: mock.MagicMock,
    mock_check_caddy: mock.MagicMock,
    mock_app_manager_class: mock.MagicMock,
    mock_caddy_manager_class: mock.MagicMock,
    mock_get_settings: mock.MagicMock,
    mock_get_admin: mock.MagicMock,
) -> None:
    mock_get_admin.return_value = mock.MagicMock()
    mock_settings = mock.MagicMock()
    mock_settings.base_domain = "example.com"
    mock_get_settings.return_value = mock_settings

    mock_caddy_manager = mock.MagicMock()
    mock_caddy_manager.get_certificates = mock.AsyncMock(return_value=[])
    mock_caddy_manager.renew_certificate = mock.AsyncMock(return_value="Renewed")
    mock_caddy_manager.add_subdomain = mock.AsyncMock(side_effect=Exception("Failed"))
    mock_caddy_manager_class.return_value = mock_caddy_manager

    mock_app_manager = mock.MagicMock()
    mock_app_manager.get_template_info.return_value = {"default_port": 8080}
    mock_app_manager_class.return_value = mock_app_manager

    mock_check_caddy.return_value = True
    mock_check_port80.return_value = True

    mock_path_instance = mock.MagicMock()
    mock_path_instance.exists.return_value = True
    mock_path_instance.read_text.return_value = "existing_caddyfile"
    mock_path.return_value = mock_path_instance

    mock_render.return_value = "rendered html"

    db_result = mock.MagicMock()
    mock_sd = mock.MagicMock()
    mock_sd.app_type = "some_app"
    db_result.scalar_one_or_none.return_value = mock_sd

    db_result2 = mock.MagicMock()
    db_result2.scalars.return_value.all.return_value = []

    db = mock.AsyncMock()
    db.execute.side_effect = [db_result, db_result2]

    req = MockRequest()

    resp = await ssl_renew(req, "test.example.com", db)

    assert resp == "rendered html"
    mock_render.assert_called_once()


def test_validate_domain_empty() -> None:
    from pit_panel.web.routes.ssl import _validate_domain

    assert _validate_domain("") is True
    assert _validate_domain("example.com") is True
    assert _validate_domain("invalid domain") is False


def test_get_acme_config_buypass() -> None:
    from pit_panel.web.routes.ssl import _get_acme_config

    assert _get_acme_config("buypass", "", "") == "issuer buypass"


def test_get_acme_config_google() -> None:
    from pit_panel.web.routes.ssl import _get_acme_config

    assert _get_acme_config("google", "key", "hmac") == 'issuer google {eab "key" "hmac"}'


def test_get_acme_config_unknown() -> None:
    from pit_panel.web.routes.ssl import _get_acme_config

    assert _get_acme_config("unknown", "", "") == ""


def test_get_acme_config_zerossl() -> None:
    from pit_panel.web.routes.ssl import _get_acme_config

    assert _get_acme_config("zerossl", "key", "hmac") == 'issuer zerossl {eab "key" "hmac"}'


def test_generate_caddyfile_invalid_domain() -> None:
    import pytest

    from pit_panel.web.routes.ssl import CaddyfileConfig, _generate_caddyfile

    config = CaddyfileConfig(email="test@example.com", domain="invalid domain", panel_sub="panel")
    with pytest.raises(ValueError, match="Invalid domain name"):
        _generate_caddyfile(config)


def test_generate_caddyfile_invalid_panel_sub() -> None:
    import pytest

    from pit_panel.web.routes.ssl import CaddyfileConfig, _generate_caddyfile

    config = CaddyfileConfig(
        email="test@example.com", domain="example.com", panel_sub="invalid sub"
    )
    with pytest.raises(ValueError, match="Invalid panel subdomain"):
        _generate_caddyfile(config)


def test_generate_caddyfile_zerossl_no_dns() -> None:
    from pit_panel.web.routes.ssl import CaddyfileConfig, _generate_caddyfile

    config = CaddyfileConfig(
        email="test@example.com",
        domain="example.com",
        panel_sub="panel",
        acme_provider="zerossl",
        eab_key_id="key",
        eab_hmac="hmac",
    )
    caddyfile = _generate_caddyfile(config)
    assert 'issuer zerossl {eab "key" "hmac"}' in caddyfile


def test_generate_caddyfile_acme_clause() -> None:
    from pit_panel.web.routes.ssl import CaddyfileConfig, _generate_caddyfile

    config = CaddyfileConfig(
        email="test@example.com",
        domain="example.com",
        panel_sub="panel",
        dns_provider="",
        acme_provider="buypass",
    )
    res = _generate_caddyfile(config)
    assert "issuer buypass" in res


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@mock.patch("pit_panel.web.routes.ssl.get_admin")
@mock.patch("pit_panel.web.routes.ssl.get_settings")
async def test_ssl_generate_invalid_domain(
    mock_get_settings: mock.MagicMock, mock_get_admin: mock.MagicMock
) -> None:
    from fastapi import Request

    from pit_panel.web.routes.ssl import SSLGenerateForm, ssl_generate

    mock_get_admin.return_value = mock.MagicMock()
    mock_settings = mock.MagicMock()
    mock_settings.effective_domain = "invalid domain"
    mock_settings.panel_subdomain = "panel"
    mock_get_settings.return_value = mock_settings

    db = mock.AsyncMock()
    form = SSLGenerateForm()

    req = mock.MagicMock(spec=Request)
    resp = await ssl_generate(req, form, db)
    assert resp.status_code == 400
    assert resp.body == b"Invalid base domain."


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@mock.patch("pit_panel.web.routes.ssl.get_admin")
@mock.patch("pit_panel.web.routes.ssl.get_settings")
async def test_ssl_generate_invalid_panel_sub(
    mock_get_settings: mock.MagicMock, mock_get_admin: mock.MagicMock
) -> None:
    from fastapi import Request

    from pit_panel.web.routes.ssl import SSLGenerateForm, ssl_generate

    mock_get_admin.return_value = mock.MagicMock()
    mock_settings = mock.MagicMock()
    mock_settings.effective_domain = "example.com"
    mock_settings.panel_subdomain = "invalid sub"
    mock_get_settings.return_value = mock_settings

    db = mock.AsyncMock()
    form = SSLGenerateForm()

    req = mock.MagicMock(spec=Request)
    resp = await ssl_generate(req, form, db)
    assert resp.status_code == 400
    assert resp.body == b"Invalid panel subdomain."


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
@mock.patch("pit_panel.web.routes.ssl.get_admin")
@mock.patch("pit_panel.web.routes.ssl.get_settings")
async def test_ssl_generate_value_error(
    mock_get_settings: mock.MagicMock, mock_get_admin: mock.MagicMock
) -> None:
    from fastapi import Request

    from pit_panel.web.routes.ssl import SSLGenerateForm, ssl_generate

    mock_get_admin.return_value = mock.MagicMock()
    mock_settings = mock.MagicMock()
    mock_settings.effective_domain = "example.com"
    mock_settings.panel_subdomain = "panel"
    mock_get_settings.return_value = mock_settings

    db = mock.AsyncMock()
    form = SSLGenerateForm(email="invalid\nemail")

    req = mock.MagicMock(spec=Request)
    resp = await ssl_generate(req, form, db)
    assert resp.status_code == 400
    assert b"Error: Invalid characters in input" in resp.body
