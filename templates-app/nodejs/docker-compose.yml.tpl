services:
  app:
    image: node:20-alpine
    restart: unless-stopped
    working_dir: /app
    ports:
      - '${PORT}:3000'
    command: sh -c "npm install && npm start || { CFG=''; for f in vite.config.ts vite.config.js; do [ -f \$f ] && echo \"import c from '/app/'\$f'; export default { ...c, server: { ...c.server, allowedHosts: true } };\" > /tmp/vc.mjs && CFG='--config /tmp/vc.mjs' && break; done; npx vite --host 0.0.0.0 --port \${PORT:-3000} \$CFG; }"
    volumes:
      - ./app:/app
