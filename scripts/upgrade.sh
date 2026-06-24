#!/bin/bash
set -euo pipefail

echo "=== pit-panel upgrade ==="
echo ""

INSTALL_DIR="/opt/pit-panel"
SERVICE="pit-panel.service"
BRANCH="${PITPANEL_BRANCH:-main}"

cd "$INSTALL_DIR"

# Check current version
CURRENT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "Current version: $CURRENT"

# Fetch latest
echo "Fetching updates..."
git fetch origin "$BRANCH" --tags

REMOTE=$(git rev-parse --short "origin/$BRANCH")
echo "Remote version:  $REMOTE"

if [ "$CURRENT" = "$REMOTE" ]; then
    echo "Already up to date."
    exit 0
fi

echo "Upgrading from $CURRENT to $REMOTE..."

# Drain mode (optional — panel handles this internally)
# systemctl kill -s SIGUSR1 pit-panel.service 2>/dev/null || true

# Apply update
git reset --hard "origin/$BRANCH"

# Update systemd units (service file might have changed)
echo "Updating systemd units..."
cp packaging/pit-panel.service /etc/systemd/system/
cp packaging/pit-panel-updater.service /etc/systemd/system/
cp packaging/pit-panel-updater.timer /etc/systemd/system/
systemctl daemon-reload

uv sync

# Run migrations
if [ -d "src/pit_panel/db/migrations" ]; then
    echo "Running database migrations..."
    uv run alembic upgrade head || echo "Migration skipped (alembic not configured)"
fi

# Restart
echo "Restarting pit-panel..."
systemctl restart "$SERVICE"

# Healthcheck
MAX_RETRIES=30
for i in $(seq 1 $MAX_RETRIES); do
    if curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1; then
        echo "Healthcheck OK after ${i}s"
        break
    fi
    if [ "$i" -eq "$MAX_RETRIES" ]; then
        echo "Healthcheck FAILED after ${MAX_RETRIES}s — rolling back"
        git reset --hard "$CURRENT"
        uv sync
        systemctl restart "$SERVICE"
        echo "Rolled back to $CURRENT"
        exit 1
    fi
    sleep 1
done

echo ""
echo "=== pit-panel upgraded to $REMOTE ==="
