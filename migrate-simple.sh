#!/bin/bash

# 🚀 Script Simple de Migraciones (solo aplica, no crea nuevas)
# =============================================================

set -e

echo "🚀 Aplicando migraciones..."
docker-compose -f docker-compose.local.yml exec backend python manage.py migrate

echo ""
echo "🔄 Reiniciando Celery..."
docker-compose -f docker-compose.local.yml restart celery-worker celery-beat

echo ""
echo "✅ ¡Listo!"

