#!/bin/bash
# Recrea el servicio WhatsApp (build) y levanta/recrea todos los servicios del compose.
# Uso: desde backtuki/  ->  ./refresh-whatsapp.sh
#      desde repo root  ->  ./backtuki/refresh-whatsapp.sh
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
COMPOSE="${COMPOSE_FILE:-docker-compose.local.yml}"
echo "Build whatsapp-service (--no-cache para incluir entrypoint) y recreando todos los servicios..."
docker compose -f "$COMPOSE" build --no-cache whatsapp-service
docker compose -f "$COMPOSE" up -d --force-recreate
echo "Listo. WhatsApp en http://localhost:3001 (logs: docker compose -f $COMPOSE logs -f whatsapp-service)"
