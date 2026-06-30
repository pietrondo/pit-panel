import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI

from pit_panel.web.app import _lifespan


@pytest.mark.asyncio
async def test_internal_lifespan_creates_cancels_task():
    app = FastAPI()

    mock_task = asyncio.Future()
    mock_task.cancel = MagicMock()

    with (
        patch("asyncio.create_task", return_value=mock_task) as mock_create,
        patch("pit_panel.core.blocklist.daily_blocklist_import", new_callable=MagicMock),
        patch("pit_panel.core.caddy.ssl_auto_renew_loop", new_callable=MagicMock),
        patch("pit_panel.core.health.docker_health_monitor_loop", new_callable=MagicMock),
        patch("pit_panel.core.backup.scheduled_backup_loop", new_callable=MagicMock),
    ):
        async with _lifespan(app):
            assert mock_create.call_count == 4
            mock_task.cancel.assert_not_called()

            # satisfy the await task
            mock_task.set_result(None)

        assert mock_task.cancel.call_count == 4
