services:
  kavita:
    image: jvmilazz0/kavita:latest
    restart: unless-stopped
    ports:
      - '${PORT}:5000'
    environment:
      TZ: Europe/Rome
    volumes:
      - kavita_config:/kavita/config
      - kavita_books:/kavita/books

volumes:
  kavita_config:
  kavita_books:
