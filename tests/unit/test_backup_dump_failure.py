"""A backup without its database must not report success."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import Settings
from pit_panel.core.backup import perform_app_backup
from pit_panel.db.models import Subdomain


@pytest.fixture
def mock_settings(tmp_path):
    settings = MagicMock(spec=Settings)
    settings.apps_dir = str(tmp_path / "apps")
    settings.data_dir = str(tmp_path / "data")
    return settings


@pytest.fixture
def mock_subdomain():
    sd = MagicMock(spec=Subdomain)
    sd.id = 1
    sd.subdomain = "testapp"
    return sd


@pytest.mark.asyncio
@patch("pit_panel.core.backup.notify_app_backup", new_callable=AsyncMock)
@patch("pit_panel.core.backup.DockerManager")
@patch("pit_panel.core.backup._get_db_service_info")
async def test_backup_fails_when_dump_fails(
    mock_get_db, mock_docker_class, _notify, tmp_path, mock_settings, mock_subdomain
):
    app_dir = Path(mock_settings.apps_dir) / mock_subdomain.subdomain
    app_dir.mkdir(parents=True, exist_ok=True)
    mock_get_db.return_value = ("db", "mysql", "myuser", "mypass", "mydb")

    docker = MagicMock()
    docker.exec_command = AsyncMock(
        return_value={"success": False, "stdout": "", "stderr": "Access denied"}
    )
    mock_docker_class.return_value = docker

    result = await perform_app_backup(mock_subdomain, AsyncMock(spec=AsyncSession), mock_settings)

    assert result["success"] is False
    assert "Access denied" in result["error"]
