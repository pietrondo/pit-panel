services:
  app:
    image: node:20-alpine
    restart: unless-stopped
    working_dir: /app
    ports:
      - '${PORT}:3000'
    command: sh -c "npm install && CFG=''; [ -f vite.config.pit.mjs ] && CFG='--config vite.config.pit.mjs'; npm start $CFG || npm run dev -- --host 0.0.0.0 $CFG"
    volumes:
      - ./app:/app
