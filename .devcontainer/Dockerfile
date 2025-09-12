# Use a standard, slim Python image as our base
FROM python:3.11-slim

# Install system dependencies, including git and the PostgreSQL client
RUN apt-get update && apt-get install -y \
    git \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for security
RUN useradd -m -s /bin/bash vscode

# Copy requirements files and install python packages for both apps
COPY requirements.txt /tmp/requirements-mud.txt
RUN pip install --no-cache-dir -r /tmp/requirements-mud.txt

COPY worldpainter/requirements.txt /tmp/requirements-wp.txt
RUN pip install --no-cache-dir -r /tmp/requirements-wp.txt

USER vscode