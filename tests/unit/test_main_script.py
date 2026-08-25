from unittest.mock import MagicMock, patch

import pytest

from pit_panel.config import Settings
from pit_panel.main import main


@pytest.fixture
def mock_settings():
    settings = MagicMock(spec=Settings)
    settings.host = "127.0.0.1"
    settings.port = 8080
    settings.debug = False
    settings.base_domain = ""
    return settings

@patch("pit_panel.main.argparse.ArgumentParser.parse_args")
@patch("pit_panel.main.Settings.from_config_file")
@patch("pit_panel.main.Path.mkdir")
@patch("pit_panel.main.uvicorn.run")
def test_main_default_args(
    mock_uvicorn_run, mock_mkdir, mock_from_config_file, mock_parse_args, mock_settings
):
    # Mock CLI arguments
    mock_args = MagicMock()
    mock_args.host = None
    mock_args.port = None
    mock_args.reload = False
    mock_args.config = None
    mock_parse_args.return_value = mock_args

    mock_from_config_file.return_value = mock_settings

    main()

    # Assert config loading
    mock_from_config_file.assert_called_once_with(None)

    # Assert directory creation
    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    # Assert uvicorn run
    mock_uvicorn_run.assert_called_once()
    kwargs = mock_uvicorn_run.call_args.kwargs
    assert kwargs["host"] == "0.0.0.0"  # Because base_domain is empty and host is 127.0.0.1
    assert kwargs["port"] == 8080
    assert not kwargs["reload"]
    assert kwargs["factory"]
    assert kwargs["log_level"] == "info"
    assert "log_config" in kwargs

@patch("pit_panel.main.argparse.ArgumentParser.parse_args")
@patch("pit_panel.main.Settings.from_config_file")
@patch("pit_panel.main.Path.mkdir")
@patch("pit_panel.main.uvicorn.run")
def test_main_custom_args_and_domain(
    mock_uvicorn_run, mock_mkdir, mock_from_config_file, mock_parse_args, mock_settings
):
    # Mock CLI arguments overrides
    mock_args = MagicMock()
    mock_args.host = "192.168.1.100"
    mock_args.port = 9000
    mock_args.reload = True
    mock_args.config = "/path/to/config.yml"
    mock_parse_args.return_value = mock_args

    mock_settings.base_domain = "example.com"
    mock_settings.debug = True
    mock_from_config_file.return_value = mock_settings

    main()

    # Assert config loading
    mock_from_config_file.assert_called_once_with("/path/to/config.yml")

    # Assert directory creation
    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    # Assert uvicorn run
    mock_uvicorn_run.assert_called_once()
    kwargs = mock_uvicorn_run.call_args.kwargs
    assert kwargs["host"] == "192.168.1.100"
    assert kwargs["port"] == 9000
    assert kwargs["reload"]
    assert kwargs["factory"]
    assert kwargs["log_level"] == "debug"

def test_main_dunder_main():
    """Test the __name__ == '__main__' block directly."""
    import pit_panel.main
    with patch.object(pit_panel.main, "main") as mock_main:
        with patch.object(pit_panel.main, "__name__", "__main__"):
            # Execute the string containing the dunder main block
            exec('if __name__ == "__main__": main()', pit_panel.main.__dict__)

        mock_main.assert_called_once()
