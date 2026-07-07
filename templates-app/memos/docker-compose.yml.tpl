services:
  memos:
    image: neosmemo/memos:stable
    restart: unless-stopped
    ports:
      - '${PORT}:5230'
    volumes:
      - memos_data:/var/opt/memos

volumes:
  memos_data:
