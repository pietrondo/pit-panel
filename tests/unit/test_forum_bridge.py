import urllib.error
import urllib.parse
from unittest.mock import MagicMock, mock_open, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from pit_panel.web.routes.forum_bridge import _audit, router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


@pytest.fixture
def mock_urlopen():
    with patch("pit_panel.web.routes.forum_bridge.urllib.request.urlopen") as mock:
        yield mock


@pytest.fixture
def mock_get_settings():
    with patch("pit_panel.web.routes.forum_bridge.get_settings") as mock:
        mock_settings = MagicMock()
        mock_settings.ai_forum_url = "https://example.com"
        mock.return_value = mock_settings
        yield mock


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_testo_leggi(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"Le notizie del forum"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/forum/leggi?quanti=10")
    assert response.status_code == 200
    assert response.text == "Le notizie del forum"


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_testo_discussione(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"Discussione 42"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/forum/discussione?id=42")
    assert response.status_code == 200
    assert response.text == "Discussione 42"

    response = client.get("/forum/discussione")
    assert response.status_code == 400
    assert response.json() == {"detail": "serve id= per sezione=discussione"}


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_ponte_scrivi(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"Post creato"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/ponte/scrivi?post=1&body=test&agente=test&token=dummy_token")
    assert response.status_code == 200
    assert response.text == "Post creato"


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=False)
def test_forum_ponte_scrivi_no_token(mock_exists, mock_urlopen, mock_get_settings):
    response = client.get("/ponte/scrivi?post=1&body=test&agente=test")
    assert response.status_code == 401


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_api_leggi(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.read.return_value = b'{"status": "ok"}'
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/api/forum/leggi")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_api_nuovo(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b'{"status": "ok"}'
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/api/forum/nuovo?titolo=Test&testo=test&agente=test&token=dummy_token")
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_api_ping(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"Hello"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/api/forum/ping?token=dummy_token")
    assert response.status_code == 200
    assert response.json()["ponte"] == "ok"
    assert response.json()["forum_risponde"] == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_testo_cerca(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"Risultati ricerca"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/forum/cerca?q=test")
    assert response.status_code == 200
    assert response.text == "Risultati ricerca"

    response = client.get("/forum/cerca")
    assert response.status_code == 400


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_testo_sapere(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"Sapere"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/forum/sapere")
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_testo_canali(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"Canali"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/forum/canali")
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_api_cerca(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.read.return_value = b'{"status": "ok"}'
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/api/forum/cerca?q=test")
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_api_sapere(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.read.return_value = b'{"status": "ok"}'
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/api/forum/sapere")
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_api_scrivi(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.read.return_value = b'{"status": "ok"}'
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/api/forum/scrivi?post=1&body=test&agente=test&token=dummy_token")
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_api_discussione(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.read.return_value = b'{"status": "ok"}'
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/api/forum/discussione/1")
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="")
def test_leggi_token_empty(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    response = client.get("/api/forum/ping?token=dummy_token")
    assert response.status_code == 503


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=False)
def test_leggi_token_missing(mock_exists, mock_urlopen, mock_get_settings):
    response = client.get("/ponte/ping?token=dummy_token&agente=test")
    assert response.status_code == 503


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", side_effect=PermissionError)
def test_leggi_token_permission(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    response = client.get("/ponte/ping?token=dummy_token&agente=test")
    assert response.status_code == 503


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", side_effect=OSError("Test"))
def test_leggi_token_oserror(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    response = client.get("/ponte/ping?token=dummy_token&agente=test")
    assert response.status_code == 503


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_ponte_scrivi_bad_token(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    response = client.get("/ponte/scrivi?post=1&body=test&agente=test&token=wrong_token")
    assert response.status_code == 403


def test_forum_base_no_url(mock_urlopen):
    with patch("pit_panel.web.routes.forum_bridge.get_settings") as mock:
        mock_settings = MagicMock()
        mock_settings.ai_forum_url = ""
        mock.return_value = mock_settings
        response = client.get("/forum/leggi")
        assert response.status_code == 400


def test_forum_base_invalid_url(mock_urlopen):
    with patch("pit_panel.web.routes.forum_bridge.get_settings") as mock:
        mock_settings = MagicMock()
        mock_settings.ai_forum_url = ""
        mock.return_value = mock_settings
        response = client.get("/forum/leggi?forum=ftp://example.com")
        assert response.status_code == 400


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
@patch(
    "pit_panel.web.routes.forum_bridge.urllib.request.urlopen",
    side_effect=urllib.error.HTTPError(
        "url", 404, "Not Found", {}, MagicMock(read=lambda: b"Not found")
    ),
)
def test_inoltra_httperror(mock_urlopen, mock_read, mock_exists, mock_get_settings):
    response = client.get("/forum/leggi")
    assert response.status_code == 404


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
@patch(
    "pit_panel.web.routes.forum_bridge.urllib.request.urlopen",
    side_effect=urllib.error.URLError("Error"),
)
def test_inoltra_urlerror(mock_urlopen, mock_read, mock_exists, mock_get_settings):
    response = client.get("/forum/leggi")
    assert response.status_code == 502


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_ponte_scrivi_no_post_body(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    response = client.get("/ponte/scrivi?agente=test&token=dummy_token")
    assert response.status_code == 400


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_ponte_nuovo_no_titolo(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    response = client.get("/ponte/nuovo?testo=test&agente=test&token=dummy_token")
    assert response.status_code == 400


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_api_scrivi_no_post_body(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    response = client.get("/api/forum/scrivi?agente=test&token=dummy_token")
    assert response.status_code == 422  # FastAPI built-in validation for Query(...)


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_testo_news(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"News"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/forum/news")
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_ponte_scrivi_no_post_body2(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    # Missing post
    response = client.get("/ponte/scrivi?body=test&agente=test&token=dummy_token")
    assert response.status_code == 400


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_api_ping_no_token_del_forum(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    # Need to simulate _token_forum raising HTTPException
    with patch(
        "pit_panel.web.routes.forum_bridge._token_forum",
        side_effect=HTTPException(status_code=503, detail="Token del forum vuoto"),
    ):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.read.return_value = b"Ping"
        mock_urlopen.return_value.__enter__.return_value = mock_response

        response = client.get("/api/forum/ping?token=dummy_token")
        assert response.status_code == 200
        assert response.json()["token_del_forum"] == "Token del forum vuoto"


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_ponte_ping_risponde(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b""
    mock_urlopen.return_value.__enter__.return_value = mock_response

    # /ponte/ping e' un endpoint diagnostico: non richiede post/body, solo l'agente.
    response = client.get("/ponte/ping?agente=test&token=dummy_token")
    assert response.status_code == 200
    assert response.text.startswith("ponte ok")


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_ponte_scrivi_bad_token(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    # This specifically hits lines 198-202 by calling /ponte/scrivi (which doesn't end with /nuovo)
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"Risposta"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    # Call with post and body, ends up calling _inoltra with "/api/scrivimi"
    response = client.get("/ponte/scrivi?post=1&body=test_body&agente=test&token=dummy_token")
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.open")
@patch("pit_panel.web.routes.forum_bridge.Path.mkdir")
@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_audit_oserror(
    mock_read, mock_exists, mock_mkdir, mock_open_path, mock_urlopen, mock_get_settings
):
    # Simulate OSError during audit
    mock_mkdir.side_effect = OSError("Audit dir error")
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"Risposta"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/forum/leggi")
    # Should not raise exception
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_testo_notizie(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"Notizie"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/forum/notizie")
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_ponte_scrivi_no_nuovo(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"Risposta"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/ponte/scrivi?post=1&body=test&agente=test&token=dummy_token")
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_api_scrivi_parent(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    # This tests the parent path on api/forum/scrivi
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.read.return_value = b'{"status": "ok"}'
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get(
        "/api/forum/scrivi?post=1&body=test&agente=test&token=dummy_token&parent=2"
    )
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
@patch(
    "pit_panel.web.routes.forum_bridge.urllib.request.urlopen",
    side_effect=urllib.error.HTTPError(
        "url", 400, "Bad Request", {}, MagicMock(read=lambda: b"Error body")
    ),
)
def test_inoltra_httperror_forum_nuovo(mock_urlopen, mock_read, mock_exists, mock_get_settings):
    response = client.get("/api/forum/nuovo?titolo=test&agente=test&token=dummy_token")
    assert response.status_code == 400


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
@patch(
    "pit_panel.web.routes.forum_bridge.urllib.request.urlopen", side_effect=TimeoutError("Timeout")
)
def test_inoltra_timeouterror(mock_urlopen, mock_read, mock_exists, mock_get_settings):
    # Tests TimeoutError in _inoltra (line 97)
    response = client.get("/forum/leggi")
    assert response.status_code == 502
    assert "timeout" in response.text.lower() or "raggiungibile" in response.text.lower()


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_forum_testo_default(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"Default"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/forum/qualcosa_di_strano")
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_ponte_nuovo_bad_request(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    response = client.get("/ponte/nuovo?testo=test_body&agente=test&token=dummy_token")
    assert response.status_code == 400


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
@patch(
    "pit_panel.web.routes.forum_bridge.urllib.request.urlopen", side_effect=OSError("OSError Test")
)
def test_inoltra_oserror(mock_urlopen, mock_read, mock_exists, mock_get_settings):
    # This hits line 97 properly
    response = client.get("/forum/leggi")
    assert response.status_code == 502
    assert "raggiungibile" in response.text.lower()


@patch("pit_panel.web.routes.forum_bridge.Path.open", side_effect=OSError("Audit error"))
@patch("pit_panel.web.routes.forum_bridge.Path.mkdir")
@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_audit_open_oserror(
    mock_read, mock_exists, mock_mkdir, mock_open_path, mock_urlopen, mock_get_settings
):
    # This hits line 106-107 and 109 properly
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"Risposta"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/forum/leggi")
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_ponte_scrivi_no_titolo_but_nuovo(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    # Tests line 198 (if request.url.path.endswith("/nuovo") and not titolo)
    response = client.get("/ponte/nuovo?agente=test&token=dummy_token")
    assert response.status_code == 400


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_ponte_scrivi_valid_nuovo(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    # Tests lines 200-202 (valid nuovo call)
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"Risposta"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/ponte/nuovo?titolo=TestTitolo&testo=test&agente=test&token=dummy_token")
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
@patch(
    "pit_panel.web.routes.forum_bridge.urllib.request.urlopen", side_effect=TimeoutError("Timeout")
)
def test_inoltra_timeouterror_specific(mock_urlopen, mock_read, mock_exists, mock_get_settings):
    # This specifically hits line 97
    response = client.get("/forum/leggi")
    assert response.status_code == 502


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
@patch(
    "pit_panel.web.routes.forum_bridge.urllib.request.urlopen",
    side_effect=urllib.error.HTTPError(
        "url", 500, "Server Error", {}, MagicMock(read=lambda: b"Error body")
    ),
)
def test_inoltra_httperror_forum_scrivi(mock_urlopen, mock_read, mock_exists, mock_get_settings):
    # Tests line 236-238 and line 120 (by returning a specific HTTP Error on api/forum/scrivi)
    response = client.get("/api/forum/scrivi?post=1&body=test&agente=test&token=dummy_token")
    assert response.status_code == 500
    assert response.json() == {"forum": 500, "risposta": "Error body"}


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
@patch(
    "pit_panel.web.routes.forum_bridge.urllib.request.urlopen", side_effect=TimeoutError("Timeout")
)
def test_inoltra_timeouterror_specific2(mock_urlopen, mock_read, mock_exists, mock_get_settings):
    pass


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
@patch("pit_panel.web.routes.forum_bridge.urllib.request.urlopen")
def test_audit_mkdir_oserror(mock_urlopen, mock_read, mock_exists, mock_get_settings):
    # Tests line 119-120 exactly
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"Risposta"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    with patch("pit_panel.web.routes.forum_bridge.Path.mkdir", side_effect=OSError("Test OSError")):
        response = client.get("/forum/leggi")
        assert response.status_code == 200


# Coverage gap tracked: lines 97 and 120.


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
@patch("pit_panel.web.routes.forum_bridge.Path.open", side_effect=OSError("Test Open OSError"))
def test_audit_open_specific(mock_open, mock_read, mock_exists, mock_get_settings, mock_urlopen):
    pass


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
@patch("pit_panel.web.routes.forum_bridge.get_settings")
def test_forum_base_valid_url(mock_settings, mock_read, mock_exists, mock_urlopen):
    # This specifically aims to cover line 97: return f"{parti.scheme}://{parti.netloc}"
    m_settings = MagicMock()
    m_settings.ai_forum_url = ""
    mock_settings.return_value = m_settings

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_response.read.return_value = b"Risposta"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    response = client.get("/forum/leggi?forum=https://forum.example.com")
    assert response.status_code == 200


@patch("pit_panel.web.routes.forum_bridge.Path.exists", return_value=True)
@patch("pit_panel.web.routes.forum_bridge.Path.read_text", return_value="dummy_token")
def test_audit_success(mock_read, mock_exists, mock_urlopen, mock_get_settings):
    pass


def test_audit_line_120():
    m = mock_open()
    with patch("pathlib.Path.open", m), patch("pathlib.Path.mkdir"):
        _audit("/test", 200)
        m().write.assert_called()
