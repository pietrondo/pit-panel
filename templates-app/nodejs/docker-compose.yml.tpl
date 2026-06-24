version: '3.8'

services:
  app:
    image: node:20-alpine
    restart: unless-stopped
    working_dir: /app
    ports:
      - '${PORT}:3000'
    command: sh -c "npm install && npm start"
    volumes:
      - ./app:/app
    environment:
      NODE_ENV: production
