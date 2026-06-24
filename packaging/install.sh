#!/bin/bash
set -euo pipefail

echo "=== pit-panel installer ==="
echo ""

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

# Clone repo
INSTALL_DIR="/opt/pit-panel"
if [ ! -d "$INSTALL_DIR" ]; then
    echo "Cloning repository..."
    git clone https://github.com/pietrondo/pit-panel.git "$INSTALL_DIR"
fi

# Setup
echo "Setting up environment..."
cd "$INSTALL_DIR"
uv sync

# Create user
if ! id pit-panel &>/dev/null; then
    useradd -r -s /bin/false -d /opt/pit-panel pit-panel
fi

# Setup directories
mkdir -p /etc/pit-panel /var/lib/pit-panel /opt/pit-panel/apps
chown -R pit-panel:pit-panel /var/lib/pit-panel /opt/pit-panel/apps

# Generate config if missing
if [ ! -f /etc/pit-panel/config.toml ]; then
    echo "Generating config..."
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    read -rp "Your domain (leave empty for nip.io auto): " BASE_DOMAIN
    read -rp "Panel subdomain [panel]: " PANEL_SUB
    PANEL_SUB=${PANEL_SUB:-panel}
    cat > /etc/pit-panel/config.toml <<EOF
secret_key = "$SECRET"
base_domain = "$BASE_DOMAIN"
panel_subdomain = "$PANEL_SUB"
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
read -rp "Admin username: " ADMIN_USER
read -rsp "Admin password: " ADMIN_PASS
echo ""
read -rp "Admin email: " ADMIN_EMAIL

uv run pit-panel-admin create-admin --username "$ADMIN_USER" --password "$ADMIN_PASS" --email "$ADMIN_EMAIL"

# Enable and start
systemctl enable --now pit-panel.service pit-panel-updater.timer

echo ""
echo "=== pit-panel installed ==="
echo "Access at: http://$(hostname -I | awk '{print $1}'):8080"
