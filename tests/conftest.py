import pytest


@pytest.fixture
def settings():
    from pit_panel.config import Settings

    return Settings(secret_key="test-secret-key-32chars-long!!", debug=True)
