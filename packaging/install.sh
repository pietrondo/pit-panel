#!/bin/bash
set -euo pipefail

# When piped from curl, stdin may not be available for read.
# Save stdin from /dev/tty if available, else use default values.
if [ -t 0 ]; then
    INPUT_TTY=/dev/tty
else
    INPUT_TTY=/dev/stdin
fi

echo "=== pit-panel installer ==="
echo ""

# Check if running interactively
INTERACTIVE=true
if [ ! -t 0 ]; then
    echo "WARNING: Non-interactive mode. Using defaults."
    echo "Run directly from a terminal for full setup:"
    echo "  wget https://raw.githubusercontent.com/pietrondo/pit-panel/main/packaging/install.sh"
    echo "  sudo bash install.sh"
    INTERACTIVE=false
fi

# Check system
if ! command -v python3 &>/dev/null; then
    echo "Installing Python..."
    apt-get update && apt-get install -y python3 python3-venv python3-pip
fi

if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v caddy &>/dev/null; then
    echo "Installing Caddy..."
    apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
    curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" | tee /etc/apt/sources.list.d/caddy-stable.list
    apt-get update && apt-get install -y caddy
fi

if ! command -v docker &>/dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | bash
fi

# Clone or update repo
INSTALL_DIR="/opt/pit-panel"
if [ ! -d "$INSTALL_DIR" ]; then
    echo "Cloning repository..."
    git clone https://github.com/pietrondo/pit-panel.git "$INSTALL_DIR"
else
    echo "Updating existing installation..."
    git config --global --add safe.directory "$INSTALL_DIR" 2>/dev/null || true
    cd "$INSTALL_DIR"
    git fetch origin main
    git reset --hard origin/main
fi

# Setup project
echo "Setting up environment..."

# Ensure host=0.0.0.0 for direct IP access when no domain
if [ -f /etc/pit-panel/config.toml ] && ! grep -q '^host = "0\.0\.0\.0"' /etc/pit-panel/config.toml 2>/dev/null; then
    sed -i '/^host =/d' /etc/pit-panel/config.toml 2>/dev/null || true
    echo 'host = "0.0.0.0"' >> /etc/pit-panel/config.toml
fi

cd "$INSTALL_DIR"
uv sync

# Create user
if ! id pit-panel &>/dev/null; then
    useradd -r -s /bin/false -d /opt/pit-panel pit-panel
fi
usermod -a -G systemd-journal pit-panel 2>/dev/null || true

# Allow pit-panel to run upgrade + restart without password
cat > /etc/sudoers.d/pit-panel <<'SUDOERS'
pit-panel ALL=(root) NOPASSWD: /usr/bin/systemctl daemon-reload
pit-panel ALL=(root) NOPASSWD: /usr/bin/systemctl restart --no-block pit-panel.service
pit-panel ALL=(root) NOPASSWD: /usr/bin/systemctl reload caddy
pit-panel ALL=(root) NOPASSWD: /usr/bin/systemctl restart caddy.service
pit-panel ALL=(root) NOPASSWD: /bin/cp /opt/pit-panel/packaging/*.service /etc/systemd/system/
pit-panel ALL=(root) NOPASSWD: /usr/sbin/usermod -a -G systemd-journal pit-panel
pit-panel ALL=(root) NOPASSWD: /usr/bin/journalctl -u pit-panel.service *
SUDOERS
chmod 440 /etc/sudoers.d/pit-panel

# Setup directories + fix permissions (venv created as root, service runs as pit-panel)
mkdir -p /etc/pit-panel /var/lib/pit-panel /opt/pit-panel/apps
chown -R pit-panel:pit-panel /opt/pit-panel /var/lib/pit-panel
chmod -R u+rwX /opt/pit-panel/.venv 2>/dev/null || true

# Defaults
BASE_DOMAIN="${PITPANEL_DOMAIN:-}"
PANEL_SUB="${PITPANEL_PANEL_SUB:-panel}"

# Generate config if missing
if [ ! -f /etc/pit-panel/config.toml ]; then
    echo "Generating config..."
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    BASE_DOMAIN=""
    PANEL_SUB="panel"
    if $INTERACTIVE; then
        read -rp "Your domain (leave empty for nip.io auto): " BASE_DOMAIN <"$INPUT_TTY"
        read -rp "Panel subdomain [panel]: " PANEL_SUB_TMP <"$INPUT_TTY"
        PANEL_SUB=${PANEL_SUB_TMP:-panel}
    else
        BASE_DOMAIN="${PITPANEL_DOMAIN:-}"
        PANEL_SUB="${PITPANEL_PANEL_SUB:-panel}"
    fi
    cat > /etc/pit-panel/config.toml <<EOF
secret_key = "$SECRET"
base_domain = "$BASE_DOMAIN"
panel_subdomain = "$PANEL_SUB"
host = "0.0.0.0"
debug = false
EOF
    chmod 640 /etc/pit-panel/config.toml
    chown root:pit-panel /etc/pit-panel/config.toml
    if [ -n "$BASE_DOMAIN" ]; then
        echo "Panel will be at: https://${PANEL_SUB}.${BASE_DOMAIN}"
    else
        echo "Panel will be at: http://$(hostname -I | awk '{print $1}'):8080"
        echo "Configure base_domain later for HTTPS"
    fi
fi

# Install systemd units
cp packaging/pit-panel.service /etc/systemd/system/
cp packaging/pit-panel-updater.service /etc/systemd/system/
cp packaging/pit-panel-updater.timer /etc/systemd/system/
systemctl daemon-reload

# Create admin user
echo ""
ADMIN_USER="${PITPANEL_ADMIN_USER:-}"
ADMIN_PASS="${PITPANEL_ADMIN_PASS:-}"
ADMIN_EMAIL="${PITPANEL_ADMIN_EMAIL:-}"

if $INTERACTIVE && [ -z "$ADMIN_USER" ]; then
    read -rp "Admin username: " ADMIN_USER <"$INPUT_TTY"
    read -rsp "Admin password: " ADMIN_PASS <"$INPUT_TTY"
    echo ""
    read -rp "Admin email: " ADMIN_EMAIL <"$INPUT_TTY"
fi

# Fallback: auto-create admin with random password
if [ -z "$ADMIN_USER" ]; then
    ADMIN_USER="admin"
    ADMIN_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(12))")
    ADMIN_EMAIL="admin@pit-panel.local"
    echo "Auto-creating admin user..."
fi

uv run pit-panel-admin create-admin --username "$ADMIN_USER" --password "$ADMIN_PASS" --email "$ADMIN_EMAIL"
echo "  Username: $ADMIN_USER"
echo "  Password: $ADMIN_PASS"

# Firewall — allow panel port if no domain (direct access)
if [ -z "${BASE_DOMAIN:-}" ] && command -v ufw &>/dev/null; then
    ufw allow 8080/tcp comment "pit-panel" 2>/dev/null || true
    echo "UFW: allowed port 8080"
fi

# Start services (will restart if already running from previous install)
systemctl enable pit-panel.service pit-panel-updater.timer 2>/dev/null || true
systemctl restart pit-panel.service 2>/dev/null || true

# Wait briefly and check status
sleep 2
if systemctl is-active --quiet pit-panel.service; then
    echo "pit-panel service is running."
else
    echo ""
    echo "=== SERVICE FAILED - last 20 log lines ==="
    journalctl -xeu pit-panel.service -n 20 --no-pager 2>/dev/null || true
    echo "=== END LOG ==="
    echo ""
fi

echo ""
echo "=== pit-panel installed ==="
echo ""
if [ -n "${BASE_DOMAIN:-}" ]; then
    echo "Panel:    https://${PANEL_SUB}.${BASE_DOMAIN}"
else
    echo "Panel:    http://$(hostname -I | awk '{print $1}'):8080"
fi
echo "Upgrade:  sudo bash /opt/pit-panel/scripts/upgrade.sh"
echo "Logs:     journalctl -xeu pit-panel.service"
