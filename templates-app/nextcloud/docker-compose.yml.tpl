services:
  nextcloud:
    image: nextcloud:latest
    restart: unless-stopped
    ports:
      - '${PORT}:80'
    environment:
      - POSTGRES_HOST=db
      - POSTGRES_DB=${DB_NAME}
      - POSTGRES_USER=${DB_USER}
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - NEXTCLOUD_ADMIN_USER=admin
      - NEXTCLOUD_ADMIN_PASSWORD=${WP_ADMIN_PASSWORD}
    volumes:
      - nextcloud_data:/var/www/html
    depends_on:
      - db

  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      - POSTGRES_DB=${DB_NAME}
      - POSTGRES_USER=${DB_USER}
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - db_data:/var/lib/postgresql/data

volumes:
  nextcloud_data:
  db_data:
