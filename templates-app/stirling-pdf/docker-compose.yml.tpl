version: '3.8'

services:
  stirling-pdf:
    image: stirlingtools/stirling-pdf:latest
    container_name: stirling-pdf-${subdomain}
    restart: unless-stopped
    ports:
      - '${PORT}:8080'
    volumes:
      - stirling-pdf-data:/usr/share/tesseract-ocr/4.00/tessdata
      - stirling-pdf-config:/configs
    environment:
      - DOCKER_ENABLE_SECURITY=false
      - INSTALL_BBOOK=false
      - LANGS=en_GB

volumes:
  stirling-pdf-data:
  stirling-pdf-config:
