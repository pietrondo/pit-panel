"""Renaming the home page must not break the editor with a 500."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pit_panel.web.routes import site_builder


@pytest.mark.asyncio
async def test_resolve_page_falls_back_when_home_slug_was_renamed():
    renamed_home = MagicMock(slug="start", title="start")
    other = MagicMock(slug="about", title="about")

    with patch.object(
        site_builder, "_site_pages", AsyncMock(return_value=[renamed_home, other])
    ):
        page, pages = await site_builder._resolve_page(AsyncMock(), MagicMock(), None)

    assert page is renamed_home
    assert pages == [renamed_home, other]
