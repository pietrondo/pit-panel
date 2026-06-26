version: '3.8'

services:
  mongodb:
    image: mongo:7
    restart: unless-stopped
    ports:
      - '${PORT}:27017'
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${DB_USER}
      MONGO_INITDB_ROOT_PASSWORD: ${DB_PASSWORD}
      MONGO_INITDB_DATABASE: ${DB_NAME}
    volumes:
      - mongo_data:/data/db

volumes:
  mongo_data:
