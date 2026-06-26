version: '3.8'

services:
  flask:
    image: python:3.12-slim
    restart: unless-stopped
    ports:
      - '${PORT}:5000'
    working_dir: /app
    volumes:
      - ./app:/app
    command: >
      sh -c "pip install flask gunicorn && gunicorn -b 0.0.0.0:5000 app:app"
    environment:
      FLASK_ENV: production
