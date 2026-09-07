# Compatibility Dockerfile; the root Dockerfile is the active development image.
FROM python:3.12-slim
WORKDIR /app
COPY requirements-dev.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
