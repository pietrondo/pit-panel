import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import Settings
from pit_panel.core.backup import _get_db_service_info, perform_app_backup, scheduled_backup_loop
from pit_panel.db.models import Subdomain


@pytest.fixture
def mock_settings(tmp_path):
    settings = MagicMock(spec=Settings)
    settings.apps_dir = str(tmp_path / "apps")
    settings.data_dir = str(tmp_path / "data")
    settings.backup_enabled = True
    settings.backup_retention_days = 7
    return settings


@pytest.fixture
def mock_subdomain():
    sd = MagicMock(spec=Subdomain)
    sd.id = 1
    sd.subdomain = "testapp"
    sd.app_type = "wordpress"
    return sd


def test_get_db_service_info_postgres(tmp_path):
    compose_path = tmp_path / "docker-compose.yml"
    env_path = tmp_path / ".env"

    compose_data = {
        "services": {
            "db": {
                "image": "postgres:15",
                "environment": {
                    "POSTGRES_USER": "${DB_USER:-pguser}",
                    "POSTGRES_PASSWORD": "$DB_PASSWORD",
                    "POSTGRES_DB": "pgdb",
                }
            }
        }
    }
    with open(compose_path, "w") as f:
        yaml.dump(compose_data, f)

    env_path.write_text("DB_PASSWORD=secretpass\n")

    result = _get_db_service_info(compose_path, env_path)
    assert result == ("db", "postgres", "pguser", "secretpass", "pgdb")

def test_get_db_service_info_mysql(tmp_path):
    compose_path = tmp_path / "docker-compose.yml"
    env_path = tmp_path / ".env"

    compose_data = {
        "services": {
            "db": {
                "image": "mysql:8",
                "environment": [
                    "MYSQL_USER=myuser",
                    "MYSQL_PASSWORD=mypass",
                    "MYSQL_DATABASE=mydb"
                ]
            }
        }
    }
    with open(compose_path, "w") as f:
        yaml.dump(compose_data, f)

    result = _get_db_service_info(compose_path, env_path)
    assert result == ("db", "mysql", "myuser", "mypass", "mydb")


def test_get_db_service_info_invalid_yaml(tmp_path):
    compose_path = tmp_path / "docker-compose.yml"
    env_path = tmp_path / ".env"

    compose_path.write_text("invalid: yaml: :")

    result = _get_db_service_info(compose_path, env_path)
    assert result is None


def test_get_db_service_info_no_services(tmp_path):
    compose_path = tmp_path / "docker-compose.yml"
    env_path = tmp_path / ".env"

    with open(compose_path, "w") as f:
        yaml.dump({"version": "3"}, f)

    result = _get_db_service_info(compose_path, env_path)
    assert result is None


@pytest.mark.asyncio
@patch("pit_panel.core.backup.notify_app_backup")
@patch("pit_panel.core.backup.DockerManager")
async def test_perform_app_backup_no_db(mock_docker, mock_notify, tmp_path, mock_settings, mock_subdomain):
    mock_db = AsyncMock(spec=AsyncSession)

    app_dir = Path(mock_settings.apps_dir) / mock_subdomain.subdomain
    app_dir.mkdir(parents=True, exist_ok=True)

    result = await perform_app_backup(mock_subdomain, mock_db, mock_settings)

    assert result["success"] is True
    assert "name" in result
    assert "size_str" in result
    assert mock_notify.called
    assert mock_db.commit.called


@pytest.mark.asyncio
@patch("pit_panel.core.backup.notify_app_backup")
@patch("pit_panel.core.backup.DockerManager")
@patch("pit_panel.core.backup._get_db_service_info")
async def test_perform_app_backup_postgres(mock_get_db, mock_docker_class, mock_notify, tmp_path, mock_settings, mock_subdomain):
    mock_db = AsyncMock(spec=AsyncSession)

    app_dir = Path(mock_settings.apps_dir) / mock_subdomain.subdomain
    app_dir.mkdir(parents=True, exist_ok=True)

    mock_get_db.return_value = ("db", "postgres", "pguser", "pgpass", "pgdb")

    mock_docker_instance = MagicMock()
    mock_docker_instance.exec_command = AsyncMock(return_value={"success": True, "stdout": "DUMP DATA"})
    mock_docker_class.return_value = mock_docker_instance

    result = await perform_app_backup(mock_subdomain, mock_db, mock_settings)

    assert result["success"] is True

    mock_docker_instance.exec_command.assert_called_once_with(
        "testapp", "db", ["pg_dump", "-U", "pguser", "pgdb"], env={"PGPASSWORD": "pgpass"}
    )

    backup_dir = Path(mock_settings.data_dir) / "backups" / mock_subdomain.subdomain
    tar_files = list(backup_dir.glob("*.tar.gz"))
    assert len(tar_files) == 1

    import tarfile
    with tarfile.open(tar_files[0], "r:gz") as tar:
        names = tar.getnames()
        assert any("database_dump.sql" in n for n in names)


@pytest.mark.asyncio
@patch("pit_panel.core.backup.notify_app_backup")
@patch("pit_panel.core.backup.DockerManager")
@patch("pit_panel.core.backup._get_db_service_info")
async def test_perform_app_backup_mysql(mock_get_db, mock_docker_class, mock_notify, tmp_path, mock_settings, mock_subdomain):
    mock_db = AsyncMock(spec=AsyncSession)

    app_dir = Path(mock_settings.apps_dir) / mock_subdomain.subdomain
    app_dir.mkdir(parents=True, exist_ok=True)

    mock_get_db.return_value = ("db", "mysql", "myuser", "mypass", "mydb")

    mock_docker_instance = MagicMock()
    mock_docker_instance.exec_command = AsyncMock(return_value={"success": True, "stdout": "DUMP DATA"})
    mock_docker_class.return_value = mock_docker_instance

    result = await perform_app_backup(mock_subdomain, mock_db, mock_settings)

    assert result["success"] is True

    mock_docker_instance.exec_command.assert_called_once_with(
        "testapp", "db", ["mysqldump", "--hex-blob", "-u", "myuser", "-pmypass", "mydb"]
    )


@pytest.mark.asyncio
@patch("pit_panel.core.backup.tarfile.open")
async def test_perform_app_backup_exception(mock_tarfile_open, tmp_path, mock_settings, mock_subdomain):
    mock_db = AsyncMock(spec=AsyncSession)

    app_dir = Path(mock_settings.apps_dir) / mock_subdomain.subdomain
    app_dir.mkdir(parents=True, exist_ok=True)

    mock_tarfile_open.side_effect = Exception("Tar failed")

    result = await perform_app_backup(mock_subdomain, mock_db, mock_settings)

    assert result["success"] is False
    assert "Tar failed" in result["error"]

    backup_dir = Path(mock_settings.data_dir) / "backups" / mock_subdomain.subdomain
    tar_files = list(backup_dir.glob("*.tar.gz"))
    assert len(tar_files) == 0


@pytest.mark.asyncio
@patch("pit_panel.config.get_settings")
@patch("pit_panel.db.session.get_sessionmaker")
@patch("asyncio.sleep")
async def test_scheduled_backup_loop_disabled(mock_sleep, mock_get_sessionmaker, mock_get_settings, mock_settings):
    mock_settings.backup_enabled = False
    mock_get_settings.return_value = mock_settings

    mock_sleep.side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await scheduled_backup_loop()

    assert mock_get_sessionmaker.called
    assert not mock_get_sessionmaker.return_value.called


@pytest.mark.asyncio
@patch("pit_panel.core.backup.perform_app_backup")
@patch("pit_panel.config.get_settings")
@patch("pit_panel.db.session.get_sessionmaker")
@patch("asyncio.sleep")
async def test_scheduled_backup_loop_enabled(mock_sleep, mock_get_sessionmaker, mock_get_settings, mock_perform, mock_settings, mock_subdomain):
    mock_get_settings.return_value = mock_settings

    mock_db_session = AsyncMock()
    mock_db_session_cm = AsyncMock()
    mock_db_session_cm.__aenter__.return_value = mock_db_session

    mock_sessionmaker = MagicMock(return_value=mock_db_session_cm)
    mock_get_sessionmaker.return_value = mock_sessionmaker

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_subdomain]
    mock_db_session.execute.return_value = mock_result

    # Create old and new backup files to test retention
    backup_dir = Path(mock_settings.data_dir) / "backups" / mock_subdomain.subdomain
    backup_dir.mkdir(parents=True, exist_ok=True)

    old_backup = backup_dir / "old.tar.gz"
    old_backup.touch()
    new_backup = backup_dir / "new.tar.gz"
    new_backup.touch()

    import time
    import os
    now = time.time()
    os.utime(old_backup, (now - 10 * 86400, now - 10 * 86400))

    mock_sleep.side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await scheduled_backup_loop()

    assert mock_perform.called

    assert not old_backup.exists()
    assert new_backup.exists()


@pytest.mark.asyncio
@patch("pit_panel.config.get_settings")
@patch("asyncio.sleep")
async def test_scheduled_backup_loop_exception(mock_sleep, mock_get_settings, mock_settings):
    mock_get_settings.side_effect = Exception("Settings failed")

    mock_sleep.side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await scheduled_backup_loop()

    assert mock_sleep.called
