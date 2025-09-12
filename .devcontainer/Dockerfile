# Use a standard base image that includes common tools
FROM mcr.microsoft.com/devcontainers/python:0-3.11

# This ARG is used by the dev container spec to automatically handle user creation
ARG USERNAME=vscode

# Copy requirements files and install python packages for both apps
COPY requirements.txt /tmp/requirements-mud.txt
RUN pip install --no-cache-dir -r /tmp/requirements-mud.txt

COPY worldpainter/requirements.txt /tmp/requirements-wp.txt
RUN pip install --no-cache-dir -r /tmp/requirements-wp.txt

# Install the PostgreSQL client for database access from the terminal
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends postgresql-client