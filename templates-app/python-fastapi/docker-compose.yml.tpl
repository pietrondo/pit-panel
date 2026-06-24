version: '3.8'

services:
  app:
    image: python:3.12-slim
    restart: unless-stopped
    working_dir: /app
    ports:
      - '${PORT}:8000'
    command: sh -c "pip install -r requirements.txt && uvicorn main:app --host 0.0.0.0 --port 8000"
    volumes:
      - ./app:/app
