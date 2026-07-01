services:
  umami:
    image: ghcr.io/umami-software/umami:postgresql-latest
    container_name: umami-${subdomain}
    restart: unless-stopped
    ports:
      - '${PORT}:3000'
    environment:
      - DATABASE_URL=postgresql://umami:${DB_PASSWORD}@umami-db:5432/umami
      - DATABASE_TYPE=postgresql
      - APP_SECRET=${DB_PASSWORD}
    depends_on:
      - umami-db
    security_opt:
      - no-new-privileges:true

  umami-db:
    image: postgres:15-alpine
    container_name: umami-db-${subdomain}
    restart: unless-stopped
    environment:
      - POSTGRES_DB=umami
      - POSTGRES_USER=umami
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - umami-db-data:/var/lib/postgresql/data
    security_opt:
      - no-new-privileges:true

volumes:
  umami-db-data:
