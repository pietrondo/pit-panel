services:
  ghost:
    image: ghost:latest
    restart: unless-stopped
    ports:
      - '${PORT}:2368'
    environment:
      database__client: mysql
      database__connection__host: db
      database__connection__user: ${DB_USER}
      database__connection__password: ${DB_PASSWORD}
      database__connection__database: ${DB_NAME}
      url: https://${SUBDOMAIN}
    volumes:
      - ghost_data:/var/lib/ghost/content
    depends_on:
      - db

  db:
    image: mysql:8.0
    restart: unless-stopped
    environment:
      MYSQL_DATABASE: ${DB_NAME}
      MYSQL_USER: ${DB_USER}
      MYSQL_PASSWORD: ${DB_PASSWORD}
      MYSQL_RANDOM_ROOT_PASSWORD: '1'
    volumes:
      - db_data:/var/lib/mysql

volumes:
  ghost_data:
  db_data:
