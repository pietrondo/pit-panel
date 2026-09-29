import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from pit_panel.web.routes.forum_bridge import router, _inoltra
from unittest.mock import patch, MagicMock

# Creating a test app bypassing heavy db dependencies
app = FastAPI()
app.include_router(router)

@pytest.fixture
def mock_inoltra():
    with patch("pit_panel.web.routes.forum_bridge._inoltra", return_value=(200, "text/plain", "Mocked content")) as mock:
        yield mock

@pytest.fixture
def mock_settings():
    with patch("pit_panel.web.routes.forum_bridge.get_settings") as mock:
        settings = MagicMock()
        settings.ai_forum_url = "http://mock_forum.com"
        mock.return_value = settings
        yield mock

@pytest.fixture
def mock_audit():
    with patch("pit_panel.web.routes.forum_bridge._audit") as mock:
        yield mock

@pytest.fixture
def mock_verifica_token():
    with patch("pit_panel.web.routes.forum_bridge._verifica_token") as mock:
        yield mock

@pytest.fixture
def mock_token_forum():
    with patch("pit_panel.web.routes.forum_bridge._token_forum", return_value="fake-token") as mock:
        yield mock

@pytest.mark.asyncio
async def test_forum_testo_default_leggi(mock_inoltra, mock_settings, mock_audit):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/forum.txt")
        assert response.status_code == 200
        assert response.text == "Mocked content"
        mock_inoltra.assert_called_once_with("http://mock_forum.com", "/api/leggi", {"quanti": "20"})

@pytest.mark.asyncio
async def test_forum_testo_sezione_discussione(mock_inoltra, mock_settings, mock_audit):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/forum/discussione?id=1")
        assert response.status_code == 200
        mock_inoltra.assert_called_once_with("http://mock_forum.com", "/api/discussione/1", {})

@pytest.mark.asyncio
async def test_forum_testo_sezione_discussione_no_id(mock_inoltra, mock_settings):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/forum/discussione")
        assert response.status_code == 400
        assert "serve id" in response.text

@pytest.mark.asyncio
async def test_forum_testo_sezione_cerca(mock_inoltra, mock_settings, mock_audit):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/forum/cerca?q=test")
        assert response.status_code == 200
        mock_inoltra.assert_called_once_with("http://mock_forum.com", "/api/cerca", {"q": "test"})

@pytest.mark.asyncio
async def test_forum_testo_sezione_cerca_no_q(mock_inoltra, mock_settings):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/forum/cerca")
        assert response.status_code == 400
        assert "serve q" in response.text

@pytest.mark.asyncio
async def test_forum_testo_sezione_sapere(mock_inoltra, mock_settings, mock_audit):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/forum/sapere?canali=5")
        assert response.status_code == 200
        mock_inoltra.assert_called_once_with("http://mock_forum.com", "/api/sapere", {"canali": "5"})

@pytest.mark.asyncio
async def test_forum_ponte_scrivi(mock_inoltra, mock_settings, mock_audit, mock_verifica_token, mock_token_forum):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/ponte/scrivi?post=1&body=test&agente=agent")
        assert response.status_code == 200
        mock_inoltra.assert_called_once_with("http://mock_forum.com", "/api/scrivimi", {"post": "1", "body": "test", "agente": "agent", "progetto": "cloud", "token": "fake-token"})

@pytest.mark.asyncio
async def test_forum_ponte_scrivi_no_post(mock_inoltra, mock_settings, mock_verifica_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/ponte/scrivi?body=test&agente=agent")
        assert response.status_code == 400
        assert "servono post=" in response.text

@pytest.mark.asyncio
async def test_forum_ponte_nuovo(mock_inoltra, mock_settings, mock_audit, mock_verifica_token, mock_token_forum):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/ponte/nuovo?titolo=title&agente=agent")
        assert response.status_code == 200
        mock_inoltra.assert_called_once_with("http://mock_forum.com", "/api/nuovo", {"titolo": "title", "testo": "", "agente": "agent", "progetto": "cloud", "canale": "generale", "token": "fake-token"})

@pytest.mark.asyncio
async def test_forum_ponte_nuovo_no_titolo(mock_inoltra, mock_settings, mock_verifica_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/ponte/nuovo?agente=agent")
        assert response.status_code == 400
        assert "serve titolo=" in response.text

@pytest.mark.asyncio
async def test_forum_ponte_ping(mock_inoltra, mock_settings, mock_audit, mock_verifica_token, mock_token_forum):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/ponte/ping?post=1&body=test&agente=agent")
        assert response.status_code == 200
        mock_inoltra.assert_called_once_with("http://mock_forum.com", "/api/scrivimi", {"post": "1", "body": "test", "agente": "agent", "progetto": "cloud", "token": "fake-token"})

@pytest.mark.asyncio
async def test_api_forum_leggi(mock_inoltra, mock_settings, mock_audit):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/forum/leggi")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_api_forum_discussione(mock_inoltra, mock_settings, mock_audit):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/forum/discussione/123")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_api_forum_cerca(mock_inoltra, mock_settings, mock_audit):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/forum/cerca?q=test")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_api_forum_sapere(mock_inoltra, mock_settings, mock_audit):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/forum/sapere")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_api_forum_scrivi(mock_inoltra, mock_settings, mock_audit, mock_verifica_token, mock_token_forum):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/forum/scrivi?post=1&body=test&agente=agent")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_api_forum_nuovo(mock_inoltra, mock_settings, mock_audit, mock_verifica_token, mock_token_forum):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/forum/nuovo?titolo=title&agente=agent")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_api_forum_ping(mock_inoltra, mock_settings, mock_audit, mock_verifica_token, mock_token_forum):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/forum/ping")
        assert response.status_code == 200
        assert response.json()["ponte"] == "ok"
