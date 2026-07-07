services:
  etherpad:
    image: etherpad/etherpad:latest
    restart: unless-stopped
    ports:
      - '${PORT}:9001'
    volumes:
      - etherpad_data:/opt/etherpad/var

volumes:
  etherpad_data:
