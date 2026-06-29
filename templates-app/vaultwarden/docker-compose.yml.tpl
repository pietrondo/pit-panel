services:
  vaultwarden:
    image: vaultwarden/server:latest
    container_name: vaultwarden-${subdomain}
    environment:
      - WEBSOCKET_ENABLED=true
    volumes:
      - vaultwarden-data:/data
    ports:
      - '${PORT}:80'
    restart: unless-stopped

volumes:
  vaultwarden-data:
