import pytest
from coverage import Coverage
import os

if __name__ == "__main__":
    cov = Coverage(source=["src.pit_panel.web.routes.subdomains"])
    cov.start()
    pytest.main(["tests/unit/routes/test_subdomains.py", "-v"])
    cov.stop()
    cov.save()
    cov.report(show_missing=True)
