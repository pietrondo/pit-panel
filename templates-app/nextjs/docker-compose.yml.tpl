services:
  nextjs:
    image: node:22-alpine
    restart: unless-stopped
    ports:
      - '${PORT}:3000'
    working_dir: /app
    volumes:
      - ./app:/app
    command: >
      sh -c "apk add --no-cache git && if [ -f package.json ]; then npm install && npm run build && npm start; else echo 'Create package.json in app/' && exit 1; fi"
    environment:
      PORT: 3000
