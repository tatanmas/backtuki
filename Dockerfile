# 🚀 ENTERPRISE DOCKERFILE - Inspirado en AuroraDev
# Tuki Platform - Optimizado para Google Cloud Run
FROM python:3.11-slim

# Version at build time (set by deploy: --build-arg APP_VERSION=$(git rev-parse --short HEAD))
ARG APP_VERSION=unknown
ENV APP_VERSION=${APP_VERSION}
# Last deploy timestamp (America/Santiago, set by deploy script)
ARG DEPLOYED_AT=unknown
ENV DEPLOYED_AT=${DEPLOYED_AT}

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    DJANGO_SETTINGS_MODULE=config.settings.cloudrun

# Create app directory
WORKDIR /app

# Install system dependencies (minimal set)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gettext \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

    # Copy entrypoint and superuser creation scripts
    COPY entrypoint.sh /entrypoint.sh
    COPY create_superuser_simple.py ./create_superuser_simple.py
RUN chmod +x /entrypoint.sh

# Create static directory and set permissions
RUN mkdir -p /app/staticfiles /app/media && \
    useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app

USER app

# Expose port
EXPOSE 8080

# Use entrypoint script (like AuroraDev)
ENTRYPOINT ["/entrypoint.sh"]
