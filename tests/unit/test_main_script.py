from unittest.mock import MagicMock, patch

from pit_panel.main import main


@patch("pit_panel.main.uvicorn.run")
@patch("pit_panel.main.Path.mkdir")
@patch("pit_panel.main.argparse.ArgumentParser.parse_args")
def test_main_default_args(mock_parse_args, mock_mkdir, mock_uvicorn_run):
    mock_args = MagicMock()
    mock_args.host = None
    mock_args.port = None
    mock_args.reload = False
    mock_args.config = None
    mock_parse_args.return_value = mock_args

    with patch("pit_panel.main.Settings.from_config_file") as mock_settings:
        mock_settings.return_value.host = "127.0.0.1"
        mock_settings.return_value.port = 8000
        mock_settings.return_value.debug = False
        mock_settings.return_value.base_domain = ""

        main()

        mock_mkdir.assert_called_with(parents=True, exist_ok=True)
        mock_uvicorn_run.assert_called_once()
        args, kwargs = mock_uvicorn_run.call_args
        assert args[0] == "pit_panel.web.app:create_app"
        assert kwargs["host"] == "0.0.0.0"
        assert kwargs["port"] == 8000
        assert not kwargs["reload"]
        assert kwargs["factory"]
        assert kwargs["log_level"] == "info"

@patch("pit_panel.main.uvicorn.run")
@patch("pit_panel.main.Path.mkdir")
@patch("pit_panel.main.argparse.ArgumentParser.parse_args")
def test_main_with_domain(mock_parse_args, mock_mkdir, mock_uvicorn_run):
    mock_args = MagicMock()
    mock_args.host = "127.0.0.1"
    mock_args.port = 8080
    mock_args.reload = True
    mock_args.config = "config.toml"
    mock_parse_args.return_value = mock_args

    with patch("pit_panel.main.Settings.from_config_file") as mock_settings:
        mock_settings.return_value.host = "127.0.0.1"
        mock_settings.return_value.port = 8000
        mock_settings.return_value.debug = True
        mock_settings.return_value.base_domain = "example.com"

        main()

        mock_mkdir.assert_called_with(parents=True, exist_ok=True)
        mock_uvicorn_run.assert_called_once()
        args, kwargs = mock_uvicorn_run.call_args
        assert args[0] == "pit_panel.web.app:create_app"
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["port"] == 8080
        assert kwargs["reload"]
        assert kwargs["factory"]
        assert kwargs["log_level"] == "debug"

@patch("pit_panel.main.uvicorn.run")
@patch("pit_panel.main.Path.mkdir")
@patch("pit_panel.main.argparse.ArgumentParser.parse_args")
def test_main_if_name_main(mock_parse_args, mock_mkdir, mock_uvicorn_run):
    import runpy
    mock_args = MagicMock()
    mock_args.host = None
    mock_args.port = None
    mock_args.reload = False
    mock_args.config = None
    mock_parse_args.return_value = mock_args

    with patch("pit_panel.main.Settings.from_config_file") as mock_settings:
        mock_settings.return_value.host = "127.0.0.1"
        mock_settings.return_value.port = 8000
        mock_settings.return_value.debug = False
        mock_settings.return_value.base_domain = ""

        runpy.run_module("pit_panel.main", run_name="__main__")

        mock_mkdir.assert_called_with(parents=True, exist_ok=True)
        mock_uvicorn_run.assert_called_once()
