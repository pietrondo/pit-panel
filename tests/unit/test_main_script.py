import contextlib
import runpy
import sys
from unittest.mock import patch

from pit_panel.main import main


def test_main_default_args():
    with (
        patch("sys.argv", ["pit-panel"]),
        patch("pit_panel.main.uvicorn.run") as mock_run,
        patch("pit_panel.main.Path.mkdir"),
        patch("pit_panel.config.Settings.from_config_file") as mock_settings,
    ):
        mock_settings.return_value.host = "127.0.0.1"
        mock_settings.return_value.port = 8000
        mock_settings.return_value.debug = False
        mock_settings.return_value.base_domain = ""

        main()

        mock_run.assert_called_once()
        # host should be 0.0.0.0 because of the check
        assert mock_run.call_args[1]["host"] == "0.0.0.0"


def test_main_custom_args():
    with (
        patch(
            "sys.argv",
            ["pit-panel", "--host", "192.168.1.1", "--port", "9000", "--reload"],
        ),
        patch("pit_panel.main.uvicorn.run") as mock_run,
        patch("pit_panel.main.Path.mkdir"),
        patch("pit_panel.config.Settings.from_config_file") as mock_settings,
    ):
        mock_settings.return_value.host = "127.0.0.1"
        mock_settings.return_value.port = 8000
        mock_settings.return_value.debug = False
        mock_settings.return_value.base_domain = "example.com"

        main()

        mock_run.assert_called_once()
        assert mock_run.call_args[1]["host"] == "192.168.1.1"
        assert mock_run.call_args[1]["port"] == 9000
        assert mock_run.call_args[1]["reload"] is True


def test_main_with_debug():
    with (
        patch("sys.argv", ["pit-panel"]),
        patch("pit_panel.main.uvicorn.run") as mock_run,
        patch("pit_panel.main.Path.mkdir"),
        patch("pit_panel.config.Settings.from_config_file") as mock_settings,
    ):
        mock_settings.return_value.host = "127.0.0.1"
        mock_settings.return_value.port = 8000
        mock_settings.return_value.debug = True
        mock_settings.return_value.base_domain = ""

        main()

        mock_run.assert_called_once()
        assert mock_run.call_args[1]["reload"] is True
        assert mock_run.call_args[1]["log_level"] == "debug"


def test_dunder_main():
    with (
        patch("sys.argv", ["pit-panel"]),
        patch("pit_panel.main.main") as mock_main,
    ):
        # Need to remove the module from sys.modules to reload it
        if "pit_panel.__main__" in sys.modules:
            del sys.modules["pit_panel.__main__"]
        import pit_panel.__main__  # noqa: F401

        mock_main.assert_called_once()


def test_main_block():
    with (
        patch("sys.argv", ["pit-panel", "--help"]),
        patch("pit_panel.main.Path.mkdir"),
        patch("pit_panel.main.uvicorn.run"),
        contextlib.suppress(SystemExit),
    ):
        runpy.run_path("src/pit_panel/main.py", run_name="__main__")


def test_main_block_direct():
    with (
        patch("sys.argv", ["pit-panel"]),
        patch("pit_panel.main.Path.mkdir"),
        patch("pit_panel.main.uvicorn.run") as mock_run,
    ):
        import pit_panel.main

        with patch.object(pit_panel.main, "__name__", "__main__"):
            # manually execute the block
            pit_panel.main.main()
            mock_run.assert_called_once()
