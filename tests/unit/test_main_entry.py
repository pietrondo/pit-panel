import runpy
import sys
from unittest.mock import MagicMock, patch


@patch("pit_panel.main.uvicorn.run")
@patch("pit_panel.main.argparse.ArgumentParser.parse_args")
@patch("pit_panel.main.Settings.from_config_file")
@patch("pit_panel.main.Path.mkdir")
def test_main_default_args(mock_mkdir, mock_from_config, mock_parse_args, mock_run):
    from pit_panel.main import main

    mock_args = MagicMock()
    mock_args.host = None
    mock_args.port = None
    mock_args.reload = False
    mock_args.config = None
    mock_parse_args.return_value = mock_args

    mock_settings = MagicMock()
    mock_settings.host = "127.0.0.1"
    mock_settings.port = 8080
    mock_settings.debug = False
    mock_settings.base_domain = "example.com"
    mock_from_config.return_value = mock_settings

    main()

    mock_from_config.assert_called_once_with(None)
    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0] == "pit_panel.web.app:create_app"
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8080
    assert not kwargs["reload"]
    assert kwargs["factory"]
    assert "log_config" in kwargs
    assert kwargs["log_level"] == "info"


@patch("pit_panel.main.uvicorn.run")
@patch("pit_panel.main.argparse.ArgumentParser.parse_args")
@patch("pit_panel.main.Settings.from_config_file")
@patch("pit_panel.main.Path.mkdir")
def test_main_custom_args(mock_mkdir, mock_from_config, mock_parse_args, mock_run):
    from pit_panel.main import main

    mock_args = MagicMock()
    mock_args.host = "0.0.0.0"
    mock_args.port = 9090
    mock_args.reload = True
    mock_args.config = "custom.ini"
    mock_parse_args.return_value = mock_args

    mock_settings = MagicMock()
    mock_settings.host = "127.0.0.1"
    mock_settings.port = 8080
    mock_settings.debug = False
    mock_settings.base_domain = "example.com"
    mock_from_config.return_value = mock_settings

    main()

    mock_from_config.assert_called_once_with("custom.ini")
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 9090
    assert kwargs["reload"]
    assert kwargs["log_level"] == "info"


@patch("pit_panel.main.uvicorn.run")
@patch("pit_panel.main.argparse.ArgumentParser.parse_args")
@patch("pit_panel.main.Settings.from_config_file")
@patch("pit_panel.main.Path.mkdir")
def test_main_no_domain_binding(mock_mkdir, mock_from_config, mock_parse_args, mock_run):
    from pit_panel.main import main

    mock_args = MagicMock()
    mock_args.host = None
    mock_args.port = None
    mock_args.reload = False
    mock_args.config = None
    mock_parse_args.return_value = mock_args

    mock_settings = MagicMock()
    mock_settings.host = "127.0.0.1"
    mock_settings.port = 8080
    mock_settings.debug = True
    mock_settings.base_domain = None
    mock_from_config.return_value = mock_settings

    main()

    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 8080
    assert kwargs["reload"]
    assert kwargs["log_level"] == "debug"


@patch("pit_panel.main.uvicorn.run")
def test_main_if_name_main(mock_run):
    with patch.object(sys, "argv", ["pit-panel"]):
        import pit_panel.main
        import pathlib
        with patch.object(pathlib.Path, "mkdir"):
            runpy.run_module("pit_panel.main", run_name="__main__")
        mock_run.assert_called_once()


def test_dunder_main():
    with (
        patch("pit_panel.main.uvicorn.run") as mock_run,
        patch.object(sys, "argv", ["pit-panel"]),
    ):
        import pathlib
        with patch.object(pathlib.Path, "mkdir"):
            runpy.run_module("pit_panel.__main__", run_name="__main__")
        mock_run.assert_called_once()
