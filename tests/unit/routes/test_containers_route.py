"""Regression tests for container data task cleanup."""

import asyncio
from types import SimpleNamespace

import pytest

from pit_panel.web.routes.containers import _get_containers_data


@pytest.mark.asyncio
async def test_get_containers_data_cancels_docker_task_when_database_fails() -> None:
    docker_started = asyncio.Event()
    docker_cleaned_up = asyncio.Event()

    async def ps_all():
        docker_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            docker_cleaned_up.set()

    async def execute(_statement):
        await docker_started.wait()
        raise RuntimeError("database failed")

    docker_mgr = SimpleNamespace(ps_all=ps_all)
    db = SimpleNamespace(execute=execute)

    with pytest.raises(RuntimeError, match="database failed"):
        await _get_containers_data(db, docker_mgr)

    assert docker_cleaned_up.is_set()


@pytest.mark.asyncio
async def test_get_containers_data_cancels_database_task_when_docker_fails() -> None:
    database_started = asyncio.Event()
    database_cleaned_up = asyncio.Event()

    async def execute(_statement):
        database_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            database_cleaned_up.set()

    async def ps_all():
        await database_started.wait()
        raise RuntimeError("docker failed")

    docker_mgr = SimpleNamespace(ps_all=ps_all)
    db = SimpleNamespace(execute=execute)

    with pytest.raises(RuntimeError, match="docker failed"):
        await _get_containers_data(db, docker_mgr)

    assert database_cleaned_up.is_set()
