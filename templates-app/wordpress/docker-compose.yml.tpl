services:
  wordpress:
    image: wordpress:latest
    restart: unless-stopped
    ports:
      - '${PORT}:80'
    environment:
      WORDPRESS_DB_HOST: db
      WORDPRESS_DB_USER: ${DB_USER}
      WORDPRESS_DB_PASSWORD: ${DB_PASSWORD}
      WORDPRESS_DB_NAME: ${DB_NAME}
    volumes:
      - wordpress_data:/var/www/html
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

  phpmyadmin:
    image: phpmyadmin:latest
    restart: unless-stopped
    ports:
      - '${PMA_PORT}:80'
    environment:
      PMA_HOST: db
      PMA_USER: ${DB_USER}
      PMA_PASSWORD: ${DB_PASSWORD}
      UPLOAD_LIMIT: 100M
    depends_on:
      - db

volumes:
  wordpress_data:
  db_data:
