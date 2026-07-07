services:
  n8n:
    image: n8nio/n8n:latest
    restart: unless-stopped
    ports:
      - '${PORT}:5678'
    environment:
      - N8N_PORT=5678
      - N8N_PROTOCOL=https
      - DB_TYPE=sqlite
    volumes:
      - n8n_data:/home/node/.n8n

volumes:
  n8n_data:
