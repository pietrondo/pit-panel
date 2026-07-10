"""Regression tests for dashboard HTMX polling markup."""

import re
from pathlib import Path

DASHBOARD_TEMPLATE = Path("src/pit_panel/web/templates/dashboard.html")


def test_stats_polling_preserves_grid_wrapper() -> None:
    template = DASHBOARD_TEMPLATE.read_text(encoding="utf-8")
    stats_grid = re.search(r'<div id="stats-grid"[^>]*>', template)

    assert stats_grid is not None
    assert 'hx-get="/stats"' in stats_grid.group()
    assert 'hx-swap="innerHTML"' in stats_grid.group()
    assert 'hx-swap="outerHTML"' not in stats_grid.group()
