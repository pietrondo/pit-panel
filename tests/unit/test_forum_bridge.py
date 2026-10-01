import pytest
from fastapi import FastAPI, HTTPException
from httpx import AsyncClient, ASGITransport
import respx
from httpx import Response
from pit_panel.web.routes.forum_bridge import router
from unittest.mock import patch, MagicMock
import os
from pathlib import Path

app = FastAPI()
app.include_router(router)

@pytest.fixture
def test_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

@pytest.mark.asyncio
async def test_forum_leggi(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
            mock_inoltra.return_value = (200, "text/plain", "test")
            response = await test_client.get("/api/forum/leggi")
            assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_leggi_400(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
            mock_inoltra.return_value = (400, "text/plain", "test")
            response = await test_client.get("/api/forum/leggi")
            assert response.status_code == 400

@pytest.mark.asyncio
async def test_forum_discussione(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
            mock_inoltra.return_value = (200, "text/plain", "test")
            response = await test_client.get("/api/forum/discussione/123")
            assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_cerca(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
            mock_inoltra.return_value = (200, "text/plain", "test")
            response = await test_client.get("/api/forum/cerca?q=test")
            assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_sapere(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
            mock_inoltra.return_value = (200, "text/plain", "test")
            response = await test_client.get("/api/forum/sapere")
            assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_scrivi(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._verifica_token') as mock_verifica:
            mock_verifica.return_value = None
            with patch('pit_panel.web.routes.forum_bridge._token_forum') as mock_token:
                mock_token.return_value = "test"
                with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
                    mock_inoltra.return_value = (200, "text/plain", "test")
                    response = await test_client.get("/api/forum/scrivi?post=123&body=test&agente=test")
                    assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_scrivi_no_parent(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._verifica_token') as mock_verifica:
            mock_verifica.return_value = None
            with patch('pit_panel.web.routes.forum_bridge._token_forum') as mock_token:
                mock_token.return_value = "test"
                with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
                    mock_inoltra.return_value = (200, "text/plain", "test")
                    response = await test_client.get("/api/forum/scrivi?post=123&body=test&agente=test&parent=123")
                    assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_nuovo(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._verifica_token') as mock_verifica:
            mock_verifica.return_value = None
            with patch('pit_panel.web.routes.forum_bridge._token_forum') as mock_token:
                mock_token.return_value = "test"
                with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
                    mock_inoltra.return_value = (200, "text/plain", "test")
                    response = await test_client.get("/api/forum/nuovo?titolo=test&testo=test&agente=test")
                    assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_ping(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._verifica_token') as mock_verifica:
            mock_verifica.return_value = None
            with patch('pit_panel.web.routes.forum_bridge._token_forum') as mock_token:
                mock_token.return_value = "test"
                with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
                    mock_inoltra.return_value = (200, "text/plain", "test")
                    response = await test_client.get("/api/forum/ping")
                    assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_ping_no_token(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._verifica_token') as mock_verifica:
            mock_verifica.return_value = None
            with patch('pit_panel.web.routes.forum_bridge._token_forum') as mock_token:
                mock_token.side_effect = HTTPException(status_code=400, detail="Manca token")
                with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
                    mock_inoltra.return_value = (200, "text/plain", "test")
                    response = await test_client.get("/api/forum/ping")
                    assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_testo_leggi(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
            mock_inoltra.return_value = (200, "text/plain", "test")
            response = await test_client.get("/forum/leggi")
            assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_testo_discussione(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
            mock_inoltra.return_value = (200, "text/plain", "test")
            response = await test_client.get("/forum/discussione?id=123")
            assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_testo_discussione_no_id(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
            mock_inoltra.return_value = (200, "text/plain", "test")
            response = await test_client.get("/forum/discussione")
            assert response.status_code == 400

@pytest.mark.asyncio
async def test_forum_testo_cerca(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
            mock_inoltra.return_value = (200, "text/plain", "test")
            response = await test_client.get("/forum/cerca?q=test")
            assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_testo_cerca_no_q(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
            mock_inoltra.return_value = (200, "text/plain", "test")
            response = await test_client.get("/forum/cerca")
            assert response.status_code == 400

@pytest.mark.asyncio
async def test_forum_testo_sapere(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
            mock_inoltra.return_value = (200, "text/plain", "test")
            response = await test_client.get("/forum/sapere")
            assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_testo_news(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
            mock_inoltra.return_value = (200, "text/plain", "test")
            response = await test_client.get("/forum/news")
            assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_testo_notizie(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
            mock_inoltra.return_value = (200, "text/plain", "test")
            response = await test_client.get("/forum/notizie")
            assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_testo_canali(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
            mock_inoltra.return_value = (200, "text/plain", "test")
            response = await test_client.get("/forum/canali")
            assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_ponte_scrivi(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._verifica_token') as mock_verifica:
            mock_verifica.return_value = None
            with patch('pit_panel.web.routes.forum_bridge._token_forum') as mock_token:
                mock_token.return_value = "test"
                with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
                    mock_inoltra.return_value = (200, "text/plain", "test")
                    response = await test_client.get("/ponte/scrivi?post=123&body=test&agente=test")
                    assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_ponte_scrivi_no_post_or_body(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._verifica_token') as mock_verifica:
            mock_verifica.return_value = None
            with patch('pit_panel.web.routes.forum_bridge._token_forum') as mock_token:
                mock_token.return_value = "test"
                with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
                    mock_inoltra.return_value = (200, "text/plain", "test")
                    response = await test_client.get("/ponte/scrivi?agente=test")
                    assert response.status_code == 400

@pytest.mark.asyncio
async def test_forum_ponte_nuovo(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._verifica_token') as mock_verifica:
            mock_verifica.return_value = None
            with patch('pit_panel.web.routes.forum_bridge._token_forum') as mock_token:
                mock_token.return_value = "test"
                with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
                    mock_inoltra.return_value = (200, "text/plain", "test")
                    response = await test_client.get("/ponte/nuovo?titolo=test&testo=test&agente=test")
                    assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_ponte_nuovo_no_titolo(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._verifica_token') as mock_verifica:
            mock_verifica.return_value = None
            with patch('pit_panel.web.routes.forum_bridge._token_forum') as mock_token:
                mock_token.return_value = "test"
                with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
                    mock_inoltra.return_value = (200, "text/plain", "test")
                    response = await test_client.get("/ponte/nuovo?agente=test")
                    assert response.status_code == 400

@pytest.mark.asyncio
async def test_forum_ponte_ping(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._verifica_token') as mock_verifica:
            mock_verifica.return_value = None
            with patch('pit_panel.web.routes.forum_bridge._token_forum') as mock_token:
                mock_token.return_value = "test"
                with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
                    mock_inoltra.return_value = (200, "text/plain", "test")
                    response = await test_client.get("/ponte/ping?post=123&body=test&agente=test")
                    assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_testo_no_forum(test_client):
    with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
        mock_inoltra.return_value = (200, "text/plain", "test")
        response = await test_client.get("/forum/leggi")
        assert response.status_code == 400

@pytest.mark.asyncio
async def test_forum_testo_bad_forum(test_client):
    with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
        mock_inoltra.return_value = (200, "text/plain", "test")
        response = await test_client.get("/forum/leggi?forum=test")
        assert response.status_code == 400

@pytest.mark.asyncio
async def test_inoltra_exception(test_client):
    with patch('urllib.request.urlopen') as mock_urlopen:
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(url="http://test", code=500, msg="test", hdrs={}, fp=None)
        response = await test_client.get("/forum/leggi?forum=http://test")
        assert response.status_code == 500

@pytest.mark.asyncio
async def test_audit_exception(test_client):
    with patch('pit_panel.web.routes.forum_bridge._forum_base') as mock_base:
        mock_base.return_value = "http://localhost:8000"
        with patch('pit_panel.web.routes.forum_bridge._inoltra') as mock_inoltra:
            mock_inoltra.return_value = (200, "text/plain", "test")
            with patch('pathlib.Path.open') as mock_open:
                mock_open.side_effect = OSError("test")
                response = await test_client.get("/forum/leggi")
                assert response.status_code == 200

@pytest.mark.asyncio
async def test_forum_token_exception():
    from pit_panel.web.routes.forum_bridge import _token_forum
    with patch('pit_panel.web.routes.forum_bridge._leggi_token') as mock_leggi:
        mock_leggi.side_effect = HTTPException(status_code=400, detail="Manca token")
        with pytest.raises(HTTPException):
            _token_forum()

@pytest.mark.asyncio
async def test_verifica_token_exception():
    from pit_panel.web.routes.forum_bridge import _verifica_token
    with patch('pit_panel.web.routes.forum_bridge._leggi_token') as mock_leggi:
        mock_leggi.side_effect = HTTPException(status_code=400, detail="Manca token")
        with pytest.raises(HTTPException):
            _verifica_token(None, None)

@pytest.mark.asyncio
async def test_verifica_token_invalid():
    from pit_panel.web.routes.forum_bridge import _verifica_token
    with patch('pit_panel.web.routes.forum_bridge._token_atteso') as mock_token:
        mock_token.return_value = "test"
        with pytest.raises(HTTPException):
            _verifica_token("invalid", None)

@pytest.mark.asyncio
async def test_verifica_token_valid():
    from pit_panel.web.routes.forum_bridge import _verifica_token
    with patch('pit_panel.web.routes.forum_bridge._token_atteso') as mock_token:
        mock_token.return_value = "test"
        _verifica_token("test", None)

@pytest.mark.asyncio
async def test_leggi_token():
    from pit_panel.web.routes.forum_bridge import _leggi_token
    with patch.object(Path, 'exists', return_value=False):
        with pytest.raises(HTTPException):
            _leggi_token(Path("test"), "test")

@pytest.mark.asyncio
async def test_leggi_token_read():
    from pit_panel.web.routes.forum_bridge import _leggi_token
    with patch.object(Path, 'exists', return_value=True):
        with patch.object(Path, 'read_text', return_value="test\n"):
            assert _leggi_token(Path("test"), "test") == "test"

@pytest.mark.asyncio
async def test_leggi_token_read_exception():
    from pit_panel.web.routes.forum_bridge import _leggi_token
    with patch.object(Path, 'exists', return_value=True):
        with patch.object(Path, 'read_text', side_effect=PermissionError("test")):
            with pytest.raises(HTTPException):
                _leggi_token(Path("test"), "test")

@pytest.mark.asyncio
async def test_leggi_token_read_exception_2():
    from pit_panel.web.routes.forum_bridge import _leggi_token
    with patch.object(Path, 'exists', return_value=True):
        with patch.object(Path, 'read_text', side_effect=OSError("test")):
            with pytest.raises(HTTPException):
                _leggi_token(Path("test"), "test")

@pytest.mark.asyncio
async def test_token_atteso():
    from pit_panel.web.routes.forum_bridge import _token_atteso
    with patch('pit_panel.web.routes.forum_bridge._leggi_token') as mock_leggi:
        mock_leggi.return_value = "test"
        assert _token_atteso() == "test"

@pytest.mark.asyncio
async def test_verifica_token_no_token():
    from pit_panel.web.routes.forum_bridge import _verifica_token
    with pytest.raises(HTTPException):
        _verifica_token(None, None)

@pytest.mark.asyncio
async def test_verifica_token_mismatch():
    from pit_panel.web.routes.forum_bridge import _verifica_token
    with patch('pit_panel.web.routes.forum_bridge._token_atteso') as mock_token:
        mock_token.return_value = "test"
        with pytest.raises(HTTPException):
            _verifica_token("wrong", None)

@pytest.mark.asyncio
async def test_forum_base_config():
    from pit_panel.web.routes.forum_bridge import _forum_base
    from pit_panel.config import Settings
    with patch('pit_panel.web.routes.forum_bridge.get_settings') as mock_settings:
        mock_settings.return_value = MagicMock(ai_forum_url="http://localhost:8000")
        assert _forum_base(None) == "http://localhost:8000"

@pytest.mark.asyncio
async def test_forum_base_no_config():
    from pit_panel.web.routes.forum_bridge import _forum_base
    with patch('pit_panel.web.routes.forum_bridge.get_settings') as mock_settings:
        mock_settings.return_value = MagicMock(ai_forum_url=None)
        with pytest.raises(HTTPException):
            _forum_base(None)

@pytest.mark.asyncio
async def test_forum_base_bad_forum():
    from pit_panel.web.routes.forum_bridge import _forum_base
    with patch('pit_panel.web.routes.forum_bridge.get_settings') as mock_settings:
        mock_settings.return_value = MagicMock(ai_forum_url=None)
        with pytest.raises(HTTPException):
            _forum_base("test")

@pytest.mark.asyncio
async def test_forum_base_good_forum():
    from pit_panel.web.routes.forum_bridge import _forum_base
    with patch('pit_panel.web.routes.forum_bridge.get_settings') as mock_settings:
        mock_settings.return_value = MagicMock(ai_forum_url=None)
        assert _forum_base("http://localhost:8000") == "http://localhost:8000"
@pytest.mark.asyncio
async def test_inoltra_ok():
    from pit_panel.web.routes.forum_bridge import _inoltra
    import io
    from http.client import HTTPResponse
    with patch('urllib.request.urlopen') as mock_urlopen:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers.get.return_value = "text/plain"
        mock_response.read.return_value = b"test"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        assert _inoltra("http://localhost:8000", "/api/leggi", {}) == (200, "text/plain", "test")

@pytest.mark.asyncio
async def test_inoltra_urlerror():
    from pit_panel.web.routes.forum_bridge import _inoltra
    import urllib.error
    with patch('urllib.request.urlopen') as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.URLError("test")
        assert _inoltra("http://localhost:8000", "/api/leggi", {}) == (502, "text/plain", "forum non raggiungibile: <urlopen error test>")
@pytest.mark.asyncio
async def test_audit_mkdir_oserror():
    from pit_panel.web.routes.forum_bridge import _audit
    with patch('pathlib.Path.mkdir') as mock_mkdir:
        mock_mkdir.side_effect = OSError("test")
        _audit("test", 200)

@pytest.mark.asyncio
async def test_leggi_token_read_unexpected_error():
    from pit_panel.web.routes.forum_bridge import _leggi_token
    from pathlib import Path
    with patch.object(Path, 'exists', return_value=True):
        with patch.object(Path, 'read_text', side_effect=ValueError("test")):
            with pytest.raises(ValueError):
                _leggi_token(Path("test"), "test")
@pytest.mark.asyncio
async def test_leggi_token_read_empty():
    from pit_panel.web.routes.forum_bridge import _leggi_token
    from pathlib import Path
    with patch.object(Path, 'exists', return_value=True):
        with patch.object(Path, 'read_text', return_value=""):
            with pytest.raises(HTTPException):
                _leggi_token(Path("test"), "test")
@pytest.mark.asyncio
async def test_audit_ok():
    from pit_panel.web.routes.forum_bridge import _audit
    with patch('pathlib.Path.mkdir') as mock_mkdir:
        with patch('pathlib.Path.open') as mock_open:
            _audit("test", 200)
            mock_open.assert_called_once()
