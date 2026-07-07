services:
  directus:
    image: directus/directus:latest
    container_name: directus-${subdomain}
    restart: unless-stopped
    ports:
      - '${PORT}:8055'
    environment:
      - KEY=${DB_PASSWORD}
      - SECRET=${DB_PASSWORD}
      - DB_CLIENT=pg
      - DB_HOST=directus-db
      - DB_PORT=5432
      - DB_DATABASE=directus
      - DB_USER=directus
      - DB_PASSWORD=${DB_PASSWORD}
      - WEBSOCKETS_ENABLED=true
      - ADMIN_EMAIL=admin@example.com
      - ADMIN_PASSWORD=${DB_PASSWORD}
    depends_on:
      - directus-db
      - directus-redis
    volumes:
      - directus-uploads:/directus/uploads
      - directus-extensions:/directus/extensions
    security_opt:
      - no-new-privileges:true

  directus-db:
    image: postgres:15-alpine
    container_name: directus-db-${subdomain}
    restart: unless-stopped
    environment:
      - POSTGRES_DB=directus
      - POSTGRES_USER=directus
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - directus-db-data:/var/lib/postgresql/data
    security_opt:
      - no-new-privileges:true

  directus-redis:
    image: redis:7-alpine
    container_name: directus-redis-${subdomain}
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true

volumes:
  directus-db-data:
  directus-uploads:
  directus-extensions:
