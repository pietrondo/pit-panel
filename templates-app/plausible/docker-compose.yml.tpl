services:
  plausible:
    image: plausible/analytics:v2.1
    container_name: plausible-${subdomain}
    restart: unless-stopped
    ports:
      - '${PORT}:8000'
    environment:
      - BASE_URL=https://${subdomain}.${base_domain}
      - SECRET_KEY_BASE=${SECRET_KEY_BASE}
      - DATABASE_URL=postgres://postgres:${DB_PASSWORD}@plausible-db:5432/plausible
      - CLICKHOUSE_DATABASE_URL=http://plausible-events:8123/plausible
    depends_on:
      - plausible-db
      - plausible-events
    security_opt:
      - no-new-privileges:true

  plausible-db:
    image: postgres:16-alpine
    container_name: plausible-db-${subdomain}
    restart: unless-stopped
    environment:
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=plausible
    volumes:
      - plausible-db-data:/var/lib/postgresql/data
    security_opt:
      - no-new-privileges:true

  plausible-events:
    image: clickhouse/clickhouse-server:24.3-alpine
    container_name: plausible-events-${subdomain}
    restart: unless-stopped
    volumes:
      - plausible-events-data:/var/lib/clickhouse
    security_opt:
      - no-new-privileges:true

volumes:
  plausible-db-data:
  plausible-events-data:
