#!/bin/bash

# Exit on error
set -e

# Wait for database to be ready
echo "Waiting for database..."
python -c "
import sys
import time
import psycopg2
while True:
    try:
        conn = psycopg2.connect(
            dbname=\"${DB_NAME}\",
            user=\"${DB_USER}\",
            password=\"${DB_PASSWORD}\",
            host=\"${DB_HOST}\",
            port=\"${DB_PORT}\"
        )
        conn.close()
        break
    except psycopg2.OperationalError:
        time.sleep(1)
        sys.stdout.write('.')
        sys.stdout.flush()
"
echo "Database is ready!"

# Run migrations
echo "Running migrations..."
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start server
echo "Starting server..."
exec "$@" 