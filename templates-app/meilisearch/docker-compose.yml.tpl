services:
  meilisearch:
    image: getmeili/meilisearch:latest
    restart: unless-stopped
    ports:
      - '${PORT}:7700'
    environment:
      - MEILI_MASTER_KEY=${DB_PASSWORD}
      - MEILI_NO_ANALYTICS=true
    volumes:
      - meili_data:/meili_data

volumes:
  meili_data:
