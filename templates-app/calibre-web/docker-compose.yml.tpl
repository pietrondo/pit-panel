services:
  calibre-web:
    image: linuxserver/calibre-web:latest
    restart: unless-stopped
    ports:
      - '${PORT}:8083'
    environment:
      PUID: 1000
      PGID: 1000
      TZ: Europe/Rome
    volumes:
      - calibre_config:/config
      - calibre_books:/books

volumes:
  calibre_config:
  calibre_books:
