services:
  app:
    image: node:20-alpine
    restart: unless-stopped
    working_dir: /app
    ports:
      - '${PORT}:3000'
    command: sh -c "npm ci || npm install && npm start || { if [ -f vite.config.pit.mjs ]; then npx vite --host 0.0.0.0 --port 3000 --config vite.config.pit.mjs; else npx vite --host 0.0.0.0 --port 3000; fi; }"
    volumes:
      - ./app:/app
