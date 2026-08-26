import argparse
from unittest.mock import patch, MagicMock
from pit_panel.main import main
from pit_panel.config import Settings

@patch("pit_panel.main.argparse.ArgumentParser")
@patch("pit_panel.main.Settings.from_config_file")
@patch("pit_panel.main.uvicorn.run")
@patch("pit_panel.main.Path")
def test_main(mock_path, mock_uvicorn_run, mock_from_config_file, mock_argument_parser):
    mock_parser = MagicMock()
    mock_argument_parser.return_value = mock_parser
    mock_args = argparse.Namespace(host="127.0.0.1", port=8000, reload=True, config="test.yml")
    mock_parser.parse_args.return_value = mock_args

    mock_settings = MagicMock(spec=Settings)
    mock_settings.host = "127.0.0.1"
    mock_settings.port = 8000
    mock_settings.debug = True
    mock_settings.base_domain = ""
    mock_from_config_file.return_value = mock_settings

    main()

    mock_from_config_file.assert_called_once_with("test.yml")
    mock_uvicorn_run.assert_called_once()

    # Check that it falls back to 0.0.0.0 if base_domain is empty and host is 127.0.0.1
    kwargs = mock_uvicorn_run.call_args.kwargs
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 8000
    assert kwargs["reload"] is True

@patch("pit_panel.main.argparse.ArgumentParser")
@patch("pit_panel.main.Settings.from_config_file")
@patch("pit_panel.main.uvicorn.run")
@patch("pit_panel.main.Path")
def test_main_with_domain(mock_path, mock_uvicorn_run, mock_from_config_file, mock_argument_parser):
    mock_parser = MagicMock()
    mock_argument_parser.return_value = mock_parser
    mock_args = argparse.Namespace(host=None, port=None, reload=False, config=None)
    mock_parser.parse_args.return_value = mock_args

    mock_settings = MagicMock(spec=Settings)
    mock_settings.host = "127.0.0.1"
    mock_settings.port = 8080
    mock_settings.debug = False
    mock_settings.base_domain = "example.com"
    mock_from_config_file.return_value = mock_settings

    main()

    mock_from_config_file.assert_called_once_with(None)
    mock_uvicorn_run.assert_called_once()

    kwargs = mock_uvicorn_run.call_args.kwargs
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8080
    assert kwargs["reload"] is False
    assert kwargs["log_level"] == "info"
