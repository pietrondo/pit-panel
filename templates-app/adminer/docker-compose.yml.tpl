version: '3.8'

services:
  adminer:
    image: adminer:4.8
    container_name: adminer-${subdomain}
    restart: unless-stopped
    ports:
      - '${PORT}:8080'
