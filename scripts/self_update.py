"""pit-panel self-updater — invoked by pit-panel-updater.timer.

Checks for upstream updates, applies them, restarts pit-panel, verifies
health, and rolls back on failure. Extracted from pit-panel-updater.service
to avoid systemd's "Unbalanced quoting" parsing error caused by multi-line
`python -c "..."` in unit files.

Exit codes:
    0  up-to-date or update applied + healthcheck passed
    1  update applied but healthcheck failed (rolled back)
    2  apply_update returned False (left unchanged)
    3  unexpected exception
"""

from __future__ import annotations

import asyncio
import subprocess
import sys

from pit_panel.config import Settings
from pit_panel.core.health import check_post_update
from pit_panel.core.updater import Updater


async def run() -> int:
    settings = Settings.from_config_file()
    updater = Updater(settings)

    sha = await updater.check_for_updates()
    if sha is None:
        print("No updates available")
        return 0

    applied = await updater.apply_update(sha)
    if not applied:
        print(f"apply_update({sha[:8]}) failed")
        return 2

    subprocess.run(
        ["sudo", "-n", "/usr/bin/systemctl", "restart", "--no-block", "pit-panel.service"],
        check=False,
    )

    ok = await check_post_update()
    if not ok:
        print("Healthcheck failed; rolling back")
        await updater.rollback()
        subprocess.run(
            ["sudo", "-n", "/usr/bin/systemctl", "restart", "--no-block", "pit-panel.service"],
            check=False,
        )
        return 1

    print(f"Updated to {sha[:8]}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(run()))
    except Exception as e:
        print(f"self_update: unexpected error: {e}", file=sys.stderr)
        sys.exit(3)
