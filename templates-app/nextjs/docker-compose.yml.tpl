version: '3.8'

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
      sh -c "if [ -f package.json ]; then npm run build && npm start; else echo 'Create package.json in app/' && exit 1; fi"
    environment:
      NODE_ENV: production
      PORT: 3000
