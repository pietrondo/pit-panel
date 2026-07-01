services:
  jsoncrack:
    image: jsoncrack/jsoncrack:latest
    restart: unless-stopped
    ports:
      - '${PORT}:8080'
