import sys
from unittest.mock import MagicMock, patch

import pytest

from pit_panel.main import main


def test_main_default_args():
    with (
        patch("sys.argv", ["pit-panel"]),
        patch("pit_panel.config.Settings.from_config_file") as mock_settings,
        patch("pathlib.Path.mkdir") as mock_mkdir,
        patch("uvicorn.run") as mock_run,
    ):
        mock_setting_instance = MagicMock()
        mock_setting_instance.host = "127.0.0.1"
        mock_setting_instance.port = 8080
        mock_setting_instance.debug = False
        mock_setting_instance.base_domain = ""
        mock_settings.return_value = mock_setting_instance

        main()

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == "pit_panel.web.app:create_app"
        assert kwargs["host"] == "0.0.0.0"
        assert kwargs["port"] == 8080
        assert kwargs["reload"] is False
        assert kwargs["log_level"] == "info"


def test_main_with_domain():
    with (
        patch("sys.argv", ["pit-panel", "--host", "192.168.1.1", "--port", "9000", "--reload"]),
        patch("pit_panel.config.Settings.from_config_file") as mock_settings,
        patch("pathlib.Path.mkdir") as mock_mkdir,
        patch("uvicorn.run") as mock_run,
    ):
        mock_setting_instance = MagicMock()
        mock_setting_instance.host = "127.0.0.1"
        mock_setting_instance.port = 8080
        mock_setting_instance.debug = True
        mock_setting_instance.base_domain = "example.com"
        mock_settings.return_value = mock_setting_instance

        main()

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == "pit_panel.web.app:create_app"
        assert kwargs["host"] == "192.168.1.1"
        assert kwargs["port"] == 9000
        assert kwargs["reload"] is True
        assert kwargs["log_level"] == "debug"


def test_dunder_main():
    with patch("sys.argv", ["pit-panel"]):
        with patch("pit_panel.main.main") as mock_main:
            if "pit_panel.__main__" in sys.modules:
                del sys.modules["pit_panel.__main__"]
            import runpy

            runpy.run_module("pit_panel.__main__", run_name="__main__")
            mock_main.assert_called_once()


def test_main_dunder_main_block():
    with (
        patch("sys.argv", ["pit-panel"]),
        patch("pit_panel.config.Settings.from_config_file") as mock_settings,
        patch("pathlib.Path.mkdir"),
        patch("uvicorn.run") as mock_run,
    ):
        if "pit_panel.main" in sys.modules:
            del sys.modules["pit_panel.main"]

        import runpy

        runpy.run_module("pit_panel.main", run_name="__main__")
        mock_run.assert_called_once()
