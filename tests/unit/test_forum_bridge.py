import pytest
from unittest.mock import patch, MagicMock
from pit_panel.web.routes.forum_bridge import _forum_base, _token_forum, _verifica_token, _inoltra, _audit, _leggi_token
from fastapi import HTTPException
import urllib.error
import urllib.request
from pathlib import Path

def test_forum_base():
    assert _forum_base("http://custom") == "http://custom"
    with pytest.raises(HTTPException) as excinfo:
         _forum_base(None)
    assert excinfo.value.status_code == 400

@patch("pit_panel.web.routes.forum_bridge._leggi_token")
def test_token_forum(mock_leggi_token):
    mock_leggi_token.return_value = "token_leggi"
    assert _token_forum() == "token_leggi"
    mock_leggi_token.assert_called_once()

@patch("pit_panel.web.routes.forum_bridge._token_atteso")
def test_verifica_token(mock_token_atteso):
    mock_token_atteso.return_value = "valid_key"
    # Check valid header
    assert _verifica_token("valid_key", None) is None
    # Check valid query param
    assert _verifica_token(None, "valid_key") is None

    # Check both missing
    with pytest.raises(HTTPException) as excinfo:
        _verifica_token(None, None)
    assert excinfo.value.status_code == 401

    # Check invalid token
    with pytest.raises(HTTPException) as excinfo:
        _verifica_token("invalid", None)
    assert excinfo.value.status_code == 403


@patch("urllib.request.urlopen")
def test_inoltra_success(mock_urlopen):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers.get.return_value = "text/plain; charset=utf-8"
    mock_response.read.return_value = b"test_response"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    status, ctype, text = _inoltra("http://base", "/api/test", {"param": "1"})
    assert status == 200
    assert ctype == "text/plain; charset=utf-8"
    assert text == "test_response"
    mock_urlopen.assert_called_once()
    req = mock_urlopen.call_args[0][0]
    assert req.full_url == "http://base/api/test?param=1"
    assert req.get_method() == "GET"

@patch("urllib.request.urlopen")
def test_inoltra_network_error(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.URLError("Network error")

    status, ctype, text = _inoltra("http://base", "/api/test", {})
    assert status == 502
    assert ctype == "text/plain"
    assert "forum non raggiungibile" in text

@patch("urllib.request.urlopen")
def test_inoltra_http_error(mock_urlopen):
    err = urllib.error.HTTPError("url", 404, "Not Found", None, None)
    err.read = MagicMock(return_value=b"Not found body")
    err.headers = MagicMock()
    err.headers.get.return_value = "text/plain"
    mock_urlopen.side_effect = err

    status, ctype, text = _inoltra("http://base", "/api/test", {})
    assert status == 404
    assert ctype == "text/plain"
    assert text == "Not found body"

def test_audit():
    with patch("pathlib.Path.mkdir"), patch("pathlib.Path.open", create=True) as mock_open:
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file
        _audit("/test", 200)
        mock_file.write.assert_called_once()
        assert "GET /test -> 200" in mock_file.write.call_args[0][0]

def test_audit_oserror():
    with patch("pathlib.Path.mkdir", side_effect=OSError("test")):
        _audit("/test", 200)
        # Should gracefully swallow

def test_leggi_token_success(tmp_path):
    token_file = tmp_path / "token.txt"
    token_file.write_text("my_secret_token\n")
    assert _leggi_token(token_file, "test_label") == "my_secret_token"

def test_leggi_token_missing(tmp_path):
    token_file = tmp_path / "token.txt"
    with pytest.raises(HTTPException) as excinfo:
        _leggi_token(token_file, "test_label")
    assert excinfo.value.status_code == 503
    assert "manca il file" in excinfo.value.detail

def test_leggi_token_oserror(tmp_path):
    token_file = tmp_path / "token.txt"
    token_file.write_text("my_secret_token\n")
    with patch("pathlib.Path.open", side_effect=OSError("test")), \
        pytest.raises(HTTPException) as excinfo:
        _leggi_token(token_file, "test_label")
    assert excinfo.value.status_code == 503
    assert "non leggibile" in excinfo.value.detail


from fastapi.testclient import TestClient
from pit_panel.web.routes.forum_bridge import router
from fastapi import FastAPI
app = FastAPI()
app.include_router(router)

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_forum_testo_discussione(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "contenuto discussione")
        response = client.get("/forum/discussione?id=123")
        assert response.status_code == 200
        assert response.text == "contenuto discussione"
        mock_inoltra.assert_called_once()
        assert mock_inoltra.call_args[0][1] == "/api/discussione/123"

def test_forum_testo_discussione_manca_id(client):
    with patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        response = client.get("/forum/discussione")
        assert response.status_code == 400
        assert "serve id=" in response.text

def test_forum_testo_cerca(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "risultati ricerca")
        response = client.get("/forum/cerca?q=test")
        assert response.status_code == 200
        assert response.text == "risultati ricerca"
        mock_inoltra.assert_called_once()
        assert mock_inoltra.call_args[0][1] == "/api/cerca"
        assert mock_inoltra.call_args[0][2] == {"q": "test"}

def test_forum_testo_cerca_manca_q(client):
    with patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        response = client.get("/forum/cerca")
        assert response.status_code == 400
        assert "serve q=" in response.text

def test_forum_testo_sapere(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "sapere")
        response = client.get("/forum/sapere?canali=10")
        assert response.status_code == 200
        assert response.text == "sapere"
        mock_inoltra.assert_called_once()
        assert mock_inoltra.call_args[0][1] == "/api/sapere"
        assert mock_inoltra.call_args[0][2] == {"canali": "10"}

def test_forum_testo_news(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "notizie")
        response = client.get("/forum/news?quanti=15")
        assert response.status_code == 200
        assert response.text == "notizie"
        mock_inoltra.assert_called_once()
        assert mock_inoltra.call_args[0][1] == "/api/news"
        assert mock_inoltra.call_args[0][2] == {"quanti": "15"}

def test_forum_testo_canali(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "canali")
        response = client.get("/forum/canali")
        assert response.status_code == 200
        assert response.text == "canali"
        mock_inoltra.assert_called_once()
        assert mock_inoltra.call_args[0][1] == "/api/canali"
        assert mock_inoltra.call_args[0][2] == {}

def test_forum_testo_leggi(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "leggi")
        response = client.get("/forum/leggi?quanti=5")
        assert response.status_code == 200
        assert response.text == "leggi"
        mock_inoltra.assert_called_once()
        assert mock_inoltra.call_args[0][1] == "/api/leggi"
        assert mock_inoltra.call_args[0][2] == {"quanti": "5"}

def test_forum_ponte_scrivi(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._verifica_token") as mock_verifica, \
         patch("pit_panel.web.routes.forum_bridge._token_forum") as mock_token, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "ok")
        mock_token.return_value = "fake_token"
        response = client.get("/ponte/scrivi?post=1&body=test&agente=test_agent")
        assert response.status_code == 200
        assert response.text == "ok"
        mock_inoltra.assert_called_once()

def test_forum_ponte_scrivi_manca_post(client):
    with patch("pit_panel.web.routes.forum_bridge._verifica_token") as mock_verifica, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        response = client.get("/ponte/scrivi?body=test&agente=test_agent")
        assert response.status_code == 400

def test_forum_ponte_nuovo(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._verifica_token") as mock_verifica, \
         patch("pit_panel.web.routes.forum_bridge._token_forum") as mock_token, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "ok")
        mock_token.return_value = "fake_token"
        response = client.get("/ponte/nuovo?titolo=test_titolo&testo=test&agente=test_agent")
        assert response.status_code == 200
        assert response.text == "ok"
        mock_inoltra.assert_called_once()
        assert mock_inoltra.call_args[0][1] == "/api/nuovo"

def test_forum_ponte_nuovo_manca_titolo(client):
    with patch("pit_panel.web.routes.forum_bridge._verifica_token") as mock_verifica, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        response = client.get("/ponte/nuovo?testo=test&agente=test_agent")
        assert response.status_code == 400

def test_forum_ponte_ping(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._verifica_token") as mock_verifica, \
         patch("pit_panel.web.routes.forum_bridge._token_forum") as mock_token, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "pong")
        mock_token.return_value = "fake_token"
        response = client.get("/ponte/ping?post=1&body=test&agente=test_agent")
        assert response.status_code == 200
        assert response.text == "pong"

def test_api_forum_leggi(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "leggi api")
        response = client.get("/api/forum/leggi")
        assert response.status_code == 200
        assert response.text == "leggi api"

def test_api_forum_discussione(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "discussione api")
        response = client.get("/api/forum/discussione/123")
        assert response.status_code == 200
        assert response.text == "discussione api"

def test_api_forum_cerca(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "cerca api")
        response = client.get("/api/forum/cerca?q=test")
        assert response.status_code == 200
        assert response.text == "cerca api"

def test_api_forum_sapere(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "sapere api")
        response = client.get("/api/forum/sapere")
        assert response.status_code == 200
        assert response.text == "sapere api"

def test_api_forum_scrivi(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._verifica_token") as mock_verifica, \
         patch("pit_panel.web.routes.forum_bridge._token_forum") as mock_token, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "scrivi api")
        mock_token.return_value = "fake_token"
        response = client.get("/api/forum/scrivi?post=1&body=test&agente=test_agent")
        assert response.status_code == 200
        assert response.json() == {"forum": 200, "risposta": "scrivi api"}

def test_api_forum_nuovo(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._verifica_token") as mock_verifica, \
         patch("pit_panel.web.routes.forum_bridge._token_forum") as mock_token, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "nuovo api")
        mock_token.return_value = "fake_token"
        response = client.get("/api/forum/nuovo?titolo=test&agente=test_agent")
        assert response.status_code == 200
        assert response.json() == {"forum": 200, "risposta": "nuovo api"}

def test_api_forum_ping(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._verifica_token") as mock_verifica, \
         patch("pit_panel.web.routes.forum_bridge._token_forum") as mock_token, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "ping api")
        mock_token.return_value = "fake_token"
        response = client.get("/api/forum/ping")
        assert response.status_code == 200
        assert response.json()["ponte"] == "ok"
        assert response.json()["anteprima"] == "ping api"

def test_forum_ponte_scrivi_no_post_body(client):
     with patch("pit_panel.web.routes.forum_bridge._verifica_token") as mock_verifica, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        response = client.get("/ponte/scrivi?agente=test_agent")
        # should fail either 422 for FastAPI missing query or 400 from our code
        assert response.status_code in (400, 422)

def test_forum_ponte_ping_token_error(client):
    with patch("pit_panel.web.routes.forum_bridge._inoltra") as mock_inoltra, \
         patch("pit_panel.web.routes.forum_bridge._verifica_token") as mock_verifica, \
         patch("pit_panel.web.routes.forum_bridge._token_forum", side_effect=HTTPException(status_code=503, detail="err")) as mock_token, \
         patch("pit_panel.web.routes.forum_bridge._forum_base", return_value="http://fake"):
        mock_inoltra.return_value = (200, "text/plain", "ping api")
        response = client.get("/api/forum/ping")
        assert response.status_code == 200
        assert response.json()["token_del_forum"] == "err"

def test_leggi_token_permission_error(tmp_path):
    token_file = tmp_path / "token.txt"
    token_file.write_text("my_secret_token\n")
    with patch("pathlib.Path.read_text", side_effect=PermissionError("test")), \
        pytest.raises(HTTPException) as excinfo:
        _leggi_token(token_file, "test_label")
    assert excinfo.value.status_code == 503
    assert "non può leggere" in excinfo.value.detail

def test_leggi_token_empty(tmp_path):
    token_file = tmp_path / "token.txt"
    token_file.write_text("\n \t \n")
    with pytest.raises(HTTPException) as excinfo:
        _leggi_token(token_file, "test_label")
    assert excinfo.value.status_code == 503
    assert "è vuoto" in excinfo.value.detail

def test_token_atteso():
    from pit_panel.web.routes.forum_bridge import _token_atteso
    with patch("pit_panel.web.routes.forum_bridge._leggi_token") as mock_leggi:
        mock_leggi.return_value = "token_atteso_valore"
        assert _token_atteso() == "token_atteso_valore"
        mock_leggi.assert_called_once()
        assert "Token del ponte" == mock_leggi.call_args[0][1]

def test_forum_base_invalid_url():
    with patch("pit_panel.config.get_settings") as mock_settings:
        mock_settings.return_value.ai_forum_url = ""
        with pytest.raises(HTTPException) as excinfo:
            _forum_base("not-a-url")
        assert excinfo.value.status_code == 400
        assert "non è un indirizzo" in excinfo.value.detail

        with pytest.raises(HTTPException) as excinfo:
            _forum_base("ftp://example.com")
        assert excinfo.value.status_code == 400
        assert "non è un indirizzo" in excinfo.value.detail

def test_forum_base_configured():
    with patch("pit_panel.web.routes.forum_bridge.get_settings") as mock_settings:
        mock_settings.return_value.ai_forum_url = "http://configured-forum.com/"
        from pit_panel.web.routes.forum_bridge import _forum_base
        assert _forum_base(None) == "http://configured-forum.com"
