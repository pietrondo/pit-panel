from typing import Any
from unittest.mock import mock_open

from pit_panel.web.routes.dashboard import _cpu_usage, _disk_usage, _server_hostname


def test_disk_usage(monkeypatch: Any) -> None:
    class MockUsage:
        free = 100 * (1024**3)
        total = 200 * (1024**3)

    monkeypatch.setattr("shutil.disk_usage", lambda _: MockUsage())
    result = _disk_usage()
    assert result == "100G free / 200G (50%)"


def test_disk_usage_exception(monkeypatch: Any) -> None:
    def raise_exc(_: str) -> None:
        raise OSError("Permission denied")

    monkeypatch.setattr("shutil.disk_usage", raise_exc)
    assert _disk_usage() == "N/A"


def test_server_hostname(monkeypatch: Any) -> None:
    import pit_panel.web.routes.dashboard as d
    monkeypatch.setattr(d, "_HOSTNAME", "test-node")
    assert _server_hostname() == "test-node"


def test_server_hostname_fallback(monkeypatch: Any) -> None:
    import pit_panel.web.routes.dashboard as d
    monkeypatch.setattr(d, "_HOSTNAME", "unknown")
    assert _server_hostname() == "unknown"


def test_server_hostname_exception(monkeypatch: Any) -> None:
    import pit_panel.web.routes.dashboard as d
    monkeypatch.setattr(d, "_HOSTNAME", "unknown")
    assert _server_hostname() == "unknown"


def test_cpu_usage(monkeypatch: Any) -> None:
    import pit_panel.web.routes.dashboard as d
    m = mock_open(read_data="1.50 2.00 3.00 1/100 1234\n")
    monkeypatch.setattr("builtins.open", m)
    monkeypatch.setattr(d, "_CPU_CORES", 4)
    result = _cpu_usage()
    assert result == {"load_1m": 1.5, "cores": 4, "pct": 38}


def test_cpu_usage_cap_100(monkeypatch: Any) -> None:
    import pit_panel.web.routes.dashboard as d
    m = mock_open(read_data="5.00 2.00 3.00 1/100 1234\n")
    monkeypatch.setattr("builtins.open", m)
    monkeypatch.setattr(d, "_CPU_CORES", 4)
    result = _cpu_usage()
    assert result == {"load_1m": 5.0, "cores": 4, "pct": 100}


def test_cpu_usage_exception(monkeypatch: Any) -> None:
    import pit_panel.web.routes.dashboard as d
    def raise_exc(*args: object, **kwargs: object) -> None:
        raise OSError("File not found")

    monkeypatch.setattr("builtins.open", raise_exc)
    monkeypatch.setattr(d, "_CPU_CORES", 4)
    result = _cpu_usage()
    assert result == {"load_1m": 0, "cores": 4, "pct": 0}
