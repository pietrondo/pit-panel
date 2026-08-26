from unittest.mock import patch

@patch("pit_panel.main.main")
def test_main_dunder(mock_main):
    # __main__.py is executed when `python -m pit_panel` is called
    import pit_panel.__main__

    mock_main.assert_called_once()
