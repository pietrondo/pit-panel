version: '3.8'

services:
  web:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - '${PORT}:80'
    volumes:
      - ./html:/usr/share/nginx/html:ro
