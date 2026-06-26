import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pit_panel.core.health import check_post_update


@pytest.mark.asyncio
async def test_check_post_update_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    # Mock httpx.AsyncClient.get
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        result = await check_post_update()

        assert result is True
        mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_check_post_update_failure_then_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        # First call raises an exception, second call returns 500, third returns 200
        mock_get.side_effect = [
            Exception("Connection error"),
            MagicMock(status_code=500),
            mock_resp,
        ]

        # We need to speed up the test by mocking asyncio.sleep
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await check_post_update()

            assert result is True
            assert mock_get.call_count == 3
            assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_check_post_update_timeout():
    # Simple state for the mock
    call_count = 0
    base_time = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC)

    def mock_now(tz=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call for deadline calculation
            return base_time
        # Subsequent calls for loop condition
        return base_time + datetime.timedelta(seconds=65)

    with patch("pit_panel.core.health.datetime") as mock_datetime:
        # We need to also patch timedelta and UTC to return the real ones
        mock_datetime.timedelta = datetime.timedelta
        mock_datetime.UTC = datetime.UTC

        # Setup the now mock
        mock_datetime.datetime.now.side_effect = mock_now

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            result = await check_post_update()

            assert result is False
            assert mock_get.call_count == 0
