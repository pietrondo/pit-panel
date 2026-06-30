services:
  wikijs:
    image: ghcr.io/requarks/wiki:latest
    restart: unless-stopped
    ports:
      - '${PORT}:3000'
    environment:
      DB_TYPE: postgres
      DB_HOST: db
      DB_PORT: 5432
      DB_USER: ${DB_USER}
      DB_PASS: ${DB_PASSWORD}
      DB_NAME: ${DB_NAME}
    volumes:
      - wikijs_data:/wiki/data
    depends_on:
      - db

  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - db_data:/var/lib/postgresql/data

volumes:
  wikijs_data:
  db_data:
