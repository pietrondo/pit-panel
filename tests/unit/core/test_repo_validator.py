import asyncio
import threading

import pytest

from pit_panel.core.repo_validator import (
    isolated_git_env,
    validate_repository_url,
    validate_repository_url_async,
)


def test_repository_validator_accepts_scp_provider_url():
    assert validate_repository_url("git@github.com:owner/repo.git")


def test_repository_validator_rejects_loopback_target():
    assert not validate_repository_url("http://127.0.0.1/repo")


def test_repository_validator_rejects_embedded_credentials():
    assert not validate_repository_url("https://user:secret@github.com/owner/repo.git")


@pytest.mark.asyncio
async def test_async_repository_validator_bounds_blocking_resolution(monkeypatch):
    def slow_validation(_url):
        return asyncio.run(asyncio.sleep(1))

    monkeypatch.setattr("pit_panel.core.repo_validator.validate_repository_url", slow_validation)
    assert await validate_repository_url_async("https://github.com/owner/repo.git", 0.01) is False


@pytest.mark.asyncio
async def test_async_validator_releases_permit_after_caller_cancellation(monkeypatch):
    limit = asyncio.Semaphore(1)
    started = threading.Event()
    release = threading.Event()

    def blocked_validation(_url):
        started.set()
        release.wait(timeout=2)
        return True

    monkeypatch.setattr("pit_panel.core.repo_validator._DNS_RESOLUTION_LIMIT", limit)
    monkeypatch.setattr("pit_panel.core.repo_validator.validate_repository_url", blocked_validation)
    task = asyncio.create_task(validate_repository_url_async("https://github.com/owner/repo.git"))
    await asyncio.to_thread(started.wait, 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert limit._value == 0
    release.set()
    for _ in range(20):
        await asyncio.sleep(0.01)
        if limit._value == 1:
            break
    assert limit._value == 1


def test_git_network_environment_ignores_global_and_system_config():
    env = isolated_git_env()
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_CONFIG_GLOBAL"]
