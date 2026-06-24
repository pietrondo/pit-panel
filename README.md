# pit-panel

VPS Management Panel — lightweight cPanel alternative for Debian.

## Features

- Subdomain management with automatic Caddy reverse proxy + wildcard TLS
- One-click app deployment (WordPress, Node.js, Python, Ghost, static)
- Docker Compose per-app isolation
- TOTP 2FA authentication
- Self-updating from GitHub
- Beautiful web GUI (HTMX + Alpine.js + Tailwind CSS)

## Quick Start (on Debian VPS)

```bash
curl -fsSL https://raw.githubusercontent.com/pietrondo/pit-panel/main/packaging/install.sh | bash
```

Then open `https://<your-domain>` and complete setup.

## Development

```bash
uv sync
uv run pre-commit install
uv run bd init
uv run python -m pit_panel --reload
```

## License

MIT
