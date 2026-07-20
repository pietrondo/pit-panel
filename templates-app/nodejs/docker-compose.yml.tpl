services:
  app:
    image: node:20-alpine
    restart: unless-stopped
    working_dir: /app
    ports:
      - '${PORT}:3000'
    command: sh -c "npm install && (npm run start || npm run dev -- --host 0.0.0.0)"
    volumes:
      - ./app:/app
