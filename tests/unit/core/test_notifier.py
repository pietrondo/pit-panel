from unittest.mock import patch

import pytest

from pit_panel.core.notifier import notify_login_failed


@pytest.mark.asyncio
@patch("pit_panel.core.notifier.send_telegram")
async def test_notify_login_failed(mock_send_telegram):
    username = "test_user"
    ip = "127.0.0.1"

    await notify_login_failed(username, ip)

    expected_msg = (
        f"⚠️ <b>Failed Login Attempt</b>\nUser: <code>{username}</code>\nIP: <code>{ip}</code>"
    )
    mock_send_telegram.assert_called_once_with(expected_msg)
