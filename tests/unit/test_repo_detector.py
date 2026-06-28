"""Tests for repo_detector stack detection."""

import pytest

from pit_panel.core.repo_detector import detect_stack


@pytest.fixture
def repo(tmp_path):
    return tmp_path


def test_detect_wordpress_by_config(repo):
    (repo / "wp-config.php").write_text("<?php")
    result = detect_stack(repo)
    assert result.stack_type == "wordpress"
    assert result.confidence == 95


def test_detect_wordpress_by_dir(repo):
    (repo / "wp-content").mkdir()
    result = detect_stack(repo)
    assert result.stack_type == "wordpress"
    assert result.confidence == 95


def test_detect_nextjs(repo):
    (repo / "package.json").write_text("{}")
    (repo / "next.config.js").write_text("")
    result = detect_stack(repo)
    assert result.stack_type == "nextjs"
    assert result.confidence == 95


def test_detect_nextjs_mjs(repo):
    (repo / "package.json").write_text("{}")
    (repo / "next.config.mjs").write_text("")
    result = detect_stack(repo)
    assert result.stack_type == "nextjs"
    assert result.confidence == 95


def test_detect_nodejs(repo):
    (repo / "package.json").write_text("{}")
    result = detect_stack(repo)
    assert result.stack_type == "nodejs"
    assert result.confidence == 85


def test_detect_python_fastapi(repo):
    (repo / "requirements.txt").write_text("fastapi")
    (repo / "main.py").write_text("from fastapi import FastAPI")
    result = detect_stack(repo)
    assert result.stack_type == "python-fastapi"
    assert result.confidence == 95


def test_detect_python_flask(repo):
    (repo / "requirements.txt").write_text("flask")
    (repo / "app.py").write_text("from flask import Flask")
    result = detect_stack(repo)
    assert result.stack_type == "python-flask"
    assert result.confidence == 95


def test_detect_python_generic(repo):
    (repo / "requirements.txt").write_text("requests")
    result = detect_stack(repo)
    assert result.stack_type == "python-flask"
    assert result.confidence == 80


def test_detect_python_pyproject(repo):
    (repo / "pyproject.toml").write_text("[project]")
    result = detect_stack(repo)
    assert "python" in result.stack_type


def test_detect_static_site(repo):
    (repo / "index.html").write_text("<html></html>")
    result = detect_stack(repo)
    assert result.stack_type == "static-nginx"
    assert result.confidence == 90


def test_detect_dockerfile(repo):
    (repo / "Dockerfile").write_text("FROM nginx")
    result = detect_stack(repo)
    assert result.stack_type == "custom-compose"


def test_detect_unknown(repo):
    (repo / "random.txt").write_text("hello")
    result = detect_stack(repo)
    assert result.confidence == 30
    assert "unknown stack" in result.indicators[0]


def test_detect_empty_repo(repo):
    result = detect_stack(repo)
    assert result.confidence == 30


def test_detect_ghost(repo):
    (repo / "Ghostfile").write_text("")
    result = detect_stack(repo)
    assert result.stack_type == "ghost"
    assert result.confidence == 90


def test_detect_ghost_by_dir(repo):
    (repo / "ghost").mkdir()
    result = detect_stack(repo)
    assert result.stack_type == "ghost"
    assert result.confidence == 90
