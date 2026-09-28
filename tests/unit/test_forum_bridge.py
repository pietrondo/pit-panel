import unittest
import urllib.error
from unittest.mock import MagicMock, mock_open, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from pit_panel.web.routes.forum_bridge import (
    _audit,
    _forum_base,
    _inoltra,
    _leggi_token,
    _token_atteso,
    _token_forum,
    _verifica_token,
)
from pit_panel.web.routes.forum_bridge import router as forum_router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(forum_router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_leggi_token(tmp_path):
    token_file = tmp_path / "token.txt"
    # missing file
    with pytest.raises(HTTPException) as exc:
        _leggi_token(token_file, "Test Token")
    assert exc.value.status_code == 503
    assert "manca il file" in exc.value.detail

    # empty file
    token_file.write_text("")
    with pytest.raises(HTTPException) as exc:
        _leggi_token(token_file, "Test Token")
    assert exc.value.status_code == 503
    assert "è vuoto" in exc.value.detail

    # valid token
    token_file.write_text("mytoken123\n")
    assert _leggi_token(token_file, "Test Token") == "mytoken123"


def test_verifica_token():
    with patch("pit_panel.web.routes.forum_bridge._token_atteso", return_value="expected_token"):
        # No token
        with pytest.raises(HTTPException) as exc:
            _verifica_token(None, None)
        assert exc.value.status_code == 401

        # Invalid token
        with pytest.raises(HTTPException) as exc:
            _verifica_token("wrong", None)
        assert exc.value.status_code == 403

        # Valid token header
        _verifica_token("expected_token", None)
        # Valid token param
        _verifica_token(None, "expected_token")


def test_forum_base():
    with patch("pit_panel.web.routes.forum_bridge.get_settings") as mock_settings:
        # Settings configured
        mock_settings.return_value.ai_forum_url = "https://config.forum/"
        assert _forum_base(None) == "https://config.forum"

        # No setting, no param
        mock_settings.return_value.ai_forum_url = None
        with pytest.raises(HTTPException) as exc:
            _forum_base(None)
        assert exc.value.status_code == 400

        # Invalid param
        with pytest.raises(HTTPException) as exc:
            _forum_base("not-a-url")
        assert exc.value.status_code == 400

        # Valid param
        assert _forum_base("https://param.forum/abc") == "https://param.forum"


def test_inoltra():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = mock_urlopen.return_value.__enter__.return_value
        mock_response.status = 200
        mock_response.headers.get.return_value = "application/json"
        mock_response.read.return_value = b'{"ok": true}'

        code, ctype, body = _inoltra("https://base", "/path", {"a": "1", "b": ""})
        assert code == 200
        assert ctype == "application/json"
        assert body == '{"ok": true}'

        mock_urlopen.side_effect = urllib.error.URLError("test")
        code, ctype, body = _inoltra("https://base", "/path", {})
        assert code == 502


def test_forum_text_read_endpoints(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra:
        mock_inoltra.return_value = (200, "text/plain", "Hello from forum")
        with patch("pit_panel.web.routes.forum_bridge._audit"):
            # test different sections
            sections = [
                ("leggi", {}, "/api/leggi"),
                ("discussione", {"id": 123}, "/api/discussione/123"),
                ("cerca", {"q": "term"}, "/api/cerca"),
                ("sapere", {}, "/api/sapere"),
                ("news", {}, "/api/news"),
                ("canali", {}, "/api/canali"),
            ]

            for section, params, expected_path in sections:
                q_params = "&".join(f"{k}={v}" for k, v in params.items())
                q_params += "&forum=https://example.com"
                url = (
                    f"/forum/{section}?{q_params}"
                    if section != "leggi"
                    else f"/forum.txt?{q_params}"
                )

                resp = client.get(url)
                assert resp.status_code == 200
                assert resp.text == "Hello from forum"
                mock_inoltra.assert_called_with(
                    "https://example.com",
                    expected_path,
                    unittest.mock.ANY
                    if expected_path != "/api/discussione/123" and expected_path != "/api/canali"
                    else {},
                )


def test_forum_ponte_scrivi_and_nuovo(client):
    with patch("pit_panel.web.routes.forum_bridge._verifica_token"):
        with patch("pit_panel.web.routes.forum_bridge._token_forum", return_value="forum_t"):
            with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra:
                mock_inoltra.return_value = (200, "text/plain", "Success")
                with patch("pit_panel.web.routes.forum_bridge._audit"):
                    # Test scrivi
                    resp = client.get(
                        "/ponte/scrivi?post=123&body=hello&agente=bot&forum=https://example.com"
                    )
                    assert resp.status_code == 200
                    mock_inoltra.assert_called_with(
                        "https://example.com",
                        "/api/scrivimi",
                        {
                            "post": "123",
                            "body": "hello",
                            "agente": "bot",
                            "progetto": "cloud",
                            "token": "forum_t",
                        },
                    )

                    # Test nuovo
                    resp = client.get(
                        "/ponte/nuovo?titolo=new&testo=hello&agente=bot&forum=https://example.com"
                    )
                    assert resp.status_code == 200
                    mock_inoltra.assert_called_with(
                        "https://example.com",
                        "/api/nuovo",
                        {
                            "titolo": "new",
                            "testo": "hello",
                            "agente": "bot",
                            "progetto": "cloud",
                            "canale": "generale",
                            "token": "forum_t",
                        },
                    )


def test_api_endpoints(client):
    with patch("pit_panel.web.routes.forum_bridge._verifica_token"):
        with patch("pit_panel.web.routes.forum_bridge._token_forum", return_value="forum_t"):
            with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra:
                mock_inoltra.return_value = (200, "application/json", '{"ok": true}')
                with patch("pit_panel.web.routes.forum_bridge._audit"):
                    # Test api/forum/leggi
                    resp = client.get("/api/forum/leggi?forum=https://example.com")
                    assert resp.status_code == 200

                    # Test api/forum/scrivi
                    resp = client.get(
                        "/api/forum/scrivi?post=1&body=h&agente=bot&forum=https://example.com"
                    )
                    assert resp.status_code == 200
                    assert resp.json() == {"forum": 200, "risposta": '{"ok": true}'}

                    # Test ping
                    resp = client.get("/api/forum/ping?forum=https://example.com")
                    assert resp.status_code == 200
                    assert resp.json()["ponte"] == "ok"


def test_forum_bridge_missing_coverage(client):
    with patch("pit_panel.web.routes.forum_bridge._verifica_token"):
        with patch("pit_panel.web.routes.forum_bridge._token_forum", return_value="forum_t"):
            with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra:
                mock_inoltra.return_value = (200, "application/json", '{"ok": true}')
                with patch("pit_panel.web.routes.forum_bridge._audit"):
                    # Test api/forum/cerca
                    resp = client.get("/api/forum/cerca?q=test&forum=https://example.com")
                    assert resp.status_code == 200

                    # Test api/forum/discussione/{id}
                    resp = client.get("/api/forum/discussione/123?forum=https://example.com")
                    assert resp.status_code == 200

                    # Test api/forum/sapere
                    resp = client.get("/api/forum/sapere?canali=5&forum=https://example.com")
                    assert resp.status_code == 200

                    # Test api/forum/nuovo
                    resp = client.get(
                        "/api/forum/nuovo?titolo=title&testo=t&agente=a&forum=https://example.com"
                    )
                    assert resp.status_code == 200

                    # forum base from config missing
                    with patch("pit_panel.web.routes.forum_bridge.get_settings") as mock_settings:
                        mock_settings.return_value.ai_forum_url = ""
                        resp = client.get("/api/forum/leggi")
                        assert resp.status_code == 400

                        resp = client.get("/api/forum/leggi?forum=not-a-url")
                        assert resp.status_code == 400


def test_forum_leggi_token_exceptions(tmp_path):
    token_file = tmp_path / "token.txt"
    token_file.write_text("mytoken123")

    with patch("pathlib.Path.read_text", side_effect=PermissionError("denied")):
        with pytest.raises(HTTPException) as exc:
            _leggi_token(token_file, "Test Token")
        assert exc.value.status_code == 503
        assert "il servizio non può leggere" in exc.value.detail

    with patch("pathlib.Path.read_text", side_effect=OSError("denied")):
        with pytest.raises(HTTPException) as exc:
            _leggi_token(token_file, "Test Token")
        assert exc.value.status_code == 503
        assert "non leggibile" in exc.value.detail


def test_audit_logs():
    with patch("pathlib.Path.open", side_effect=OSError("test error")):
        # This shouldn't raise since OSError is caught in _audit
        _audit("/api/leggi", 200)


def test_forum_bridge_remaining_branches(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra:
        mock_inoltra.return_value = (200, "text/plain", "Success")
        with patch("pit_panel.web.routes.forum_bridge._audit"):
            # test forum.txt missing discussione id
            resp = client.get("/forum/discussione?forum=https://example.com")
            assert resp.status_code == 400

            # test forum.txt missing cerca q
            resp = client.get("/forum/cerca?forum=https://example.com")
            assert resp.status_code == 400

    with patch("pit_panel.web.routes.forum_bridge._verifica_token"):
        with patch("pit_panel.web.routes.forum_bridge._token_forum", return_value="forum_t"):
            with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra:
                mock_inoltra.return_value = (200, "text/plain", "Success")
                with patch("pit_panel.web.routes.forum_bridge._audit"):
                    # test ponte nuovo missing titolo
                    resp = client.get("/ponte/nuovo?agente=bot&forum=https://example.com")
                    assert resp.status_code == 400

                    # test ponte scrivi missing post/body
                    resp = client.get("/ponte/scrivi?agente=bot&forum=https://example.com")
                    assert resp.status_code == 400


def test_forum_bridge_token_fail(client):
    with patch("pit_panel.web.routes.forum_bridge._verifica_token"):
        with patch(
            "pit_panel.web.routes.forum_bridge._token_forum",
            side_effect=HTTPException(status_code=503, detail="err"),
        ):
            with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra:
                mock_inoltra.return_value = (200, "text/plain", "Success")
                with patch("pit_panel.web.routes.forum_bridge._audit"):
                    resp = client.get("/api/forum/ping?forum=https://example.com")
                    assert resp.status_code == 200
                    assert resp.json()["token_del_forum"] == "err"


def test_inoltra_http_error():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_error = urllib.error.HTTPError("url", 404, "Not Found", {}, mock_urlopen)
        mock_error.read = MagicMock(return_value=b"Not Found Error")
        mock_urlopen.side_effect = mock_error

        code, ctype, body = _inoltra("https://base", "/path", {})
        assert code == 404
        assert body == "Not Found Error"


def test_forum_ponte_ping(client):
    with patch("pit_panel.web.routes.forum_bridge._verifica_token"):
        with patch("pit_panel.web.routes.forum_bridge._token_forum", return_value="forum_t"):
            with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra:
                mock_inoltra.return_value = (200, "text/plain", "pong")
                with patch("pit_panel.web.routes.forum_bridge._audit"):
                    resp = client.get(
                        "/ponte/ping?post=123&body=h&agente=bot&forum=https://example.com"
                    )
                    assert resp.status_code == 200
                    assert resp.text == "pong"


def test_inoltra_url_encode():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = mock_urlopen.return_value.__enter__.return_value
        mock_response.status = 200
        mock_response.headers.get.return_value = "application/json"
        mock_response.read.return_value = b'{"ok": true}'

        # Test with no params to hit `f"{base}{percorso}"` without `?`
        code, ctype, body = _inoltra("https://base", "/path", {"empty": ""})
        assert code == 200
        assert mock_urlopen.call_args[0][0].full_url == "https://base/path"


def test_forum_bridge_remaining_lines(tmp_path):
    with patch("pit_panel.web.routes.forum_bridge.get_settings") as mock_settings:
        mock_settings.return_value.forum_token_path = str(tmp_path / "token1")
        mock_settings.return_value.forum_ai_token_path = str(tmp_path / "token2")
        (tmp_path / "token1").write_text("t1")
        (tmp_path / "token2").write_text("t2")

        assert _token_atteso() == "t1"
        assert _token_forum() == "t2"

    with patch("pathlib.Path.mkdir"), patch("pathlib.Path.open", mock_open()) as mock_file:
        _audit("/path", 200)
        mock_file().write.assert_called()


def test_forum_scrivi_parent(client):
    with patch("pit_panel.web.routes.forum_bridge._verifica_token"):
        with patch("pit_panel.web.routes.forum_bridge._token_forum", return_value="forum_t"):
            with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra:
                mock_inoltra.return_value = (200, "application/json", '{"ok": true}')
                with patch("pit_panel.web.routes.forum_bridge._audit"):
                    resp = client.get(
                        "/api/forum/scrivi?post=1&body=h&agente=bot&parent=2&forum=https://example.com"
                    )
                    assert resp.status_code == 200
                    mock_inoltra.assert_called_with(
                        "https://example.com",
                        "/api/scrivimi",
                        {
                            "post": "1",
                            "body": "h",
                            "agente": "bot",
                            "progetto": "cloud",
                            "token": "forum_t",
                            "parent": "2",
                        },
                    )
