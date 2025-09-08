# Use a standard, slim Python image as our base
FROM python:3.11-slim

# Install system dependencies, including git and the PostgreSQL client
# We still install the client so we can connect to external DBs later.
RUN apt-get update && apt-get install -y \
    git \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for security
RUN useradd -m -s /bin/bash vscode

# Copy requirements file and install python packages
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

USER vscode