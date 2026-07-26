services:
  stump:
    image: aaronleopold/stump:latest
    restart: unless-stopped
    ports:
      - '${PORT}:10801'
    environment:
      PUID: "1000"
      PGID: "1000"
      STUMP_CONFIG_DIR: /config
      TZ: Europe/Rome
    volumes:
      - ./config:/config
      - ./data:/data
