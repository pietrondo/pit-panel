services:
  uptime-kuma:
    image: louislam/uptime-kuma:1
    container_name: uptime-kuma-${subdomain}
    volumes:
      - uptime-kuma-data:/app/data
      - /var/run/docker.sock:/var/run/docker.sock:ro
    ports:
      - '${PORT}:3001'
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true

volumes:
  uptime-kuma-data:
