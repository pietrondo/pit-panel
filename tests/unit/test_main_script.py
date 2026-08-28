from unittest.mock import MagicMock, patch

from pit_panel.main import main


def test_main_default_args():
    with (
        patch("sys.argv", ["pit_panel"]),
        patch("pit_panel.main.uvicorn.run") as mock_run,
        patch("pit_panel.main.Path.mkdir") as mock_mkdir,
        patch("pit_panel.config.Settings.from_config_file") as mock_settings,
    ):
        mock_settings.return_value = MagicMock(
            host="127.0.0.1", port=8000, debug=False, base_domain="example.com"
        )

        main()

        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == "pit_panel.web.app:create_app"
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["port"] == 8000
        assert kwargs["reload"] is False
        assert kwargs["factory"] is True
        assert kwargs["log_level"] == "info"


def test_main_with_args():
    with (
        patch("sys.argv", ["pit_panel", "--host", "0.0.0.0", "--port", "9000", "--reload"]),
        patch("pit_panel.main.uvicorn.run") as mock_run,
        patch("pit_panel.main.Path.mkdir"),
        patch("pit_panel.config.Settings.from_config_file") as mock_settings,
    ):
        mock_settings.return_value = MagicMock(
            host="127.0.0.1", port=8000, debug=False, base_domain="example.com"
        )

        main()

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert kwargs["host"] == "0.0.0.0"
        assert kwargs["port"] == 9000
        assert kwargs["reload"] is True


def test_main_no_domain_bind_all():
    with (
        patch("sys.argv", ["pit_panel"]),
        patch("pit_panel.main.uvicorn.run") as mock_run,
        patch("pit_panel.main.Path.mkdir"),
        patch("pit_panel.config.Settings.from_config_file") as mock_settings,
    ):
        # Base domain is None and host is 127.0.0.1 -> should change to 0.0.0.0
        mock_settings.return_value = MagicMock(
            host="127.0.0.1", port=8000, debug=True, base_domain=None
        )

        main()

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert kwargs["host"] == "0.0.0.0"
        assert kwargs["log_level"] == "debug"


def test_dunder_main():
    with patch("pit_panel.main.main") as mock_main:
        import importlib

        import pit_panel.__main__

        importlib.reload(pit_panel.__main__)
        mock_main.assert_called()
