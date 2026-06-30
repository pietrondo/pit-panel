services:
  code-server:
    image: codercom/code-server:latest
    restart: unless-stopped
    ports:
      - '${PORT}:8443'
    environment:
      PASSWORD: ${CS_PASSWORD}
      DEFAULT_WORKSPACE: /workspace
    volumes:
      - code_server_data:/workspace

volumes:
  code_server_data:
