from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSendTelegram:
    @pytest.mark.asyncio
    async def test_send_telegram_no_config(self, monkeypatch):
        from pit_panel.config import Settings

        s = Settings(secret_key="test", telegram_bot_token="", telegram_chat_id="")
        monkeypatch.setattr("pit_panel.core.notifier.get_settings", lambda: s)
        from pit_panel.core.notifier import send_telegram

        result = await send_telegram("test message")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_telegram_success(self, monkeypatch):
        from pit_panel.config import Settings

        s = Settings(
            secret_key="test",
            telegram_bot_token="fake-token",
            telegram_chat_id="123456",
        )
        monkeypatch.setattr("pit_panel.core.notifier.get_settings", lambda: s)

        mock_response = MagicMock()
        mock_response.status_code = 200

        async def mock_post(*args, **kwargs):
            return mock_response

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = mock_post

        with patch("httpx.AsyncClient", return_value=mock_client):
            from pit_panel.core.notifier import send_telegram

            result = await send_telegram("test message")
            assert result is True

    @pytest.mark.asyncio
    async def test_send_telegram_http_error(self, monkeypatch):
        from pit_panel.config import Settings

        s = Settings(
            secret_key="test",
            telegram_bot_token="fake-token",
            telegram_chat_id="123456",
        )
        monkeypatch.setattr("pit_panel.core.notifier.get_settings", lambda: s)

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        async def mock_post(*args, **kwargs):
            return mock_response

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = mock_post

        with patch("httpx.AsyncClient", return_value=mock_client):
            from pit_panel.core.notifier import send_telegram

            result = await send_telegram("test message")
            assert result is False

    @pytest.mark.asyncio
    async def test_send_telegram_exception(self, monkeypatch):
        from pit_panel.config import Settings

        s = Settings(
            secret_key="test",
            telegram_bot_token="fake-token",
            telegram_chat_id="123456",
        )
        monkeypatch.setattr("pit_panel.core.notifier.get_settings", lambda: s)

        with patch("httpx.AsyncClient", side_effect=Exception("Network error")):
            from pit_panel.core.notifier import send_telegram

            result = await send_telegram("test message")
            assert result is False


class TestNotifyFunctions:
    def _patch_send(self, monkeypatch):
        mock = AsyncMock(return_value=True)
        monkeypatch.setattr("pit_panel.core.notifier.send_telegram", mock)
        return mock

    @pytest.mark.asyncio
    async def test_notify_app_backup(self, monkeypatch):
        mock = self._patch_send(monkeypatch)
        from pit_panel.core.notifier import notify_app_backup

        await notify_app_backup("myapp", "backup1", "1.2 MB")
        mock.assert_called_once()
        call_msg = mock.call_args[0][0]
        assert "myapp" in call_msg
        assert "backup1" in call_msg
        assert "1.2 MB" in call_msg

    @pytest.mark.asyncio
    async def test_notify_app_update(self, monkeypatch):
        mock = self._patch_send(monkeypatch)
        from pit_panel.core.notifier import notify_app_update

        await notify_app_update("myapp")
        mock.assert_called_once()
        assert "myapp" in mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_notify_app_deploy(self, monkeypatch):
        mock = self._patch_send(monkeypatch)
        from pit_panel.core.notifier import notify_app_deploy

        await notify_app_deploy("myapp", "wordpress", "myapp.example.com")
        mock.assert_called_once()
        msg = mock.call_args[0][0]
        assert "myapp" in msg
        assert "wordpress" in msg
        assert "myapp.example.com" in msg

    @pytest.mark.asyncio
    async def test_notify_app_delete(self, monkeypatch):
        mock = self._patch_send(monkeypatch)
        from pit_panel.core.notifier import notify_app_delete

        await notify_app_delete("myapp", "nodejs")
        mock.assert_called_once()
        msg = mock.call_args[0][0]
        assert "myapp" in msg
        assert "nodejs" in msg

    @pytest.mark.asyncio
    async def test_notify_login_failed(self, monkeypatch):
        mock = self._patch_send(monkeypatch)
        from pit_panel.core.notifier import notify_login_failed

        await notify_login_failed("admin", "1.2.3.4")
        mock.assert_called_once()
        msg = mock.call_args[0][0]
        assert "admin" in msg
        assert "1.2.3.4" in msg

    @pytest.mark.asyncio
    async def test_notify_login_success(self, monkeypatch):
        mock = self._patch_send(monkeypatch)
        from pit_panel.core.notifier import notify_login_success

        await notify_login_success("admin", "1.2.3.4")
        mock.assert_called_once()
        msg = mock.call_args[0][0]
        assert "admin" in msg
        assert "1.2.3.4" in msg

    @pytest.mark.asyncio
    async def test_notify_ssl_expiring(self, monkeypatch):
        mock = self._patch_send(monkeypatch)
        from pit_panel.core.notifier import notify_ssl_expiring

        await notify_ssl_expiring(["a.com", "b.com"], 14)
        mock.assert_called_once()
        msg = mock.call_args[0][0]
        assert "a.com" in msg
        assert "14d" in msg

    @pytest.mark.asyncio
    async def test_notify_ssl_expiring_truncates(self, monkeypatch):
        mock = self._patch_send(monkeypatch)
        from pit_panel.core.notifier import notify_ssl_expiring

        await notify_ssl_expiring(["a.com", "b.com", "c.com", "d.com", "e.com"], 7)
        mock.assert_called_once()
        msg = mock.call_args[0][0]
        assert "(+2 more)" in msg

    @pytest.mark.asyncio
    async def test_notify_system_alarm(self, monkeypatch):
        mock = self._patch_send(monkeypatch)
        from pit_panel.core.notifier import notify_system_alarm

        await notify_system_alarm("CPU overload", "95% usage")
        mock.assert_called_once()
        msg = mock.call_args[0][0]
        assert "CPU overload" in msg
        assert "95%" in msg

    @pytest.mark.asyncio
    async def test_notify_test(self, monkeypatch):
        mock = self._patch_send(monkeypatch)
        from pit_panel.core.notifier import notify_test

        result = await notify_test()
        assert result is True
        mock.assert_called_once()
