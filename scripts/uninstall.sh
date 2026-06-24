#!/bin/bash
set -euo pipefail

echo "=== pit-panel uninstall ==="
read -rp "This will remove pit-panel and all data. Continue? [y/N] " CONFIRM
if [ "${CONFIRM,,}" != "y" ]; then
    echo "Aborted."
    exit 0
fi

echo "Stopping services..."
systemctl stop pit-panel.service pit-panel-updater.timer 2>/dev/null || true
systemctl disable pit-panel.service pit-panel-updater.timer 2>/dev/null || true

echo "Removing systemd units..."
rm -f /etc/systemd/system/pit-panel.service
rm -f /etc/systemd/system/pit-panel-updater.service
rm -f /etc/systemd/system/pit-panel-updater.timer
systemctl daemon-reload

echo "Removing files..."
rm -rf /opt/pit-panel
rm -rf /etc/pit-panel
rm -rf /var/lib/pit-panel

echo "Removing user..."
userdel pit-panel 2>/dev/null || true

echo ""
echo "=== pit-panel uninstalled ==="
echo "Docker containers and /opt/pit-panel/apps/ were kept."
