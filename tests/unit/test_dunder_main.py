from unittest.mock import patch


@patch("pit_panel.main.main")
def test_dunder_main(mock_main):
    import runpy
    runpy.run_module("pit_panel.__main__", run_name="__main__")
    mock_main.assert_called_once()
