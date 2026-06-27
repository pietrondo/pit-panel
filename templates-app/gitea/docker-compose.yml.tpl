version: '3.8'

services:
  server:
    image: gitea/gitea:1.21
    container_name: gitea-${subdomain}
    environment:
      - USER_UID=1000
      - USER_GID=1000
      - GITEA__database__DB_TYPE=mysql
      - GITEA__database__HOST=db:3306
      - GITEA__database__NAME=gitea
      - GITEA__database__USER=gitea
      - GITEA__database__PASSWD=gitea
    restart: unless-stopped
    volumes:
      - gitea-data:/data
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
    ports:
      - '${PORT}:3000'
      - '2222:22'
    depends_on:
      - db

  db:
    image: mysql:8
    container_name: gitea-db-${subdomain}
    restart: unless-stopped
    environment:
      - MYSQL_ROOT_PASSWORD=gitea_root
      - MYSQL_USER=gitea
      - MYSQL_PASSWORD=gitea
      - MYSQL_DATABASE=gitea
    volumes:
      - gitea-db-data:/var/lib/mysql

volumes:
  gitea-data:
  gitea-db-data:
