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
    monkeypatch.setattr("pit_panel.web.routes.dashboard._STATIC_HOSTNAME", "test-node")
    assert _server_hostname() == "test-node"


def test_server_hostname_fallback(monkeypatch: Any) -> None:
    monkeypatch.setattr("pit_panel.web.routes.dashboard._STATIC_HOSTNAME", "unknown")
    assert _server_hostname() == "unknown"


def test_server_hostname_exception(monkeypatch: Any) -> None:
    monkeypatch.setattr("pit_panel.web.routes.dashboard._STATIC_HOSTNAME", "unknown")
    assert _server_hostname() == "unknown"


def test_cpu_usage(monkeypatch: Any) -> None:
    m = mock_open(read_data="1.50 2.00 3.00 1/100 1234\n")
    monkeypatch.setattr("builtins.open", m)
    monkeypatch.setattr("pit_panel.web.routes.dashboard._STATIC_CPU_CORES", 4)
    result = _cpu_usage()
    assert result == {"load_1m": 1.5, "cores": 4, "pct": 38}


def test_cpu_usage_cap_100(monkeypatch: Any) -> None:
    m = mock_open(read_data="5.00 2.00 3.00 1/100 1234\n")
    monkeypatch.setattr("builtins.open", m)
    monkeypatch.setattr("pit_panel.web.routes.dashboard._STATIC_CPU_CORES", 4)
    result = _cpu_usage()
    assert result == {"load_1m": 5.0, "cores": 4, "pct": 100}


def test_cpu_usage_exception(monkeypatch: Any) -> None:
    def raise_exc(*args: object, **kwargs: object) -> None:
        raise OSError("File not found")

    monkeypatch.setattr("builtins.open", raise_exc)
    monkeypatch.setattr("pit_panel.web.routes.dashboard._STATIC_CPU_CORES", 4)
    result = _cpu_usage()
    assert result == {"load_1m": 0, "cores": 4, "pct": 0}


def test_ram_usage(monkeypatch: Any) -> None:
    from pit_panel.web.routes.dashboard import _ram_usage

    monkeypatch.setattr("pit_panel.web.routes.dashboard._STATIC_OS", "Linux")
    # Wait, 8192 kB total, 4096 kB available
    m = mock_open(read_data="MemTotal: 8192000 kB\nMemFree: 2048000 kB\nMemAvailable: 4096000 kB\n")
    monkeypatch.setattr("builtins.open", m)
    result = _ram_usage()
    # 8192000 // 1024 = 8000 MB. 4096000 // 1024 = 4000 MB.
    # used = 8000 - 4000 = 4000 MB.
    # total_gb = round(8000 / 1024, 1) = 7.8
    # used_gb = round(4000 / 1024, 1) = 3.9
    # pct = 50
    assert result == {"total_gb": 7.8, "used_gb": 3.9, "pct": 50}


def test_ram_usage_exception(monkeypatch: Any) -> None:
    from pit_panel.web.routes.dashboard import _ram_usage

    monkeypatch.setattr("pit_panel.web.routes.dashboard._STATIC_OS", "Linux")

    def raise_exc(*args: object, **kwargs: object) -> None:
        raise OSError("File not found")

    monkeypatch.setattr("builtins.open", raise_exc)
    result = _ram_usage()
    assert result == {"total_gb": 0, "used_gb": 0, "pct": 0}
