import os

import pytest

# Set default test paths before any config is loaded
os.environ["PITPANEL_DATA_DIR"] = "/tmp/pit-panel-data"
os.environ["PITPANEL_APPS_DIR"] = "/tmp/pit-panel-apps"


@pytest.fixture
def settings():
    from pit_panel.config import Settings

    return Settings(secret_key="test-secret-key-32chars-long!!", debug=True)
