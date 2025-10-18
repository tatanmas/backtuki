#!/bin/bash
# Ver logs de Celery Worker en tiempo real con filtros útiles
echo "🔍 Celery Worker - Logs en vivo (Ctrl+C para salir)"
echo "=================================================="
gcloud logging tail "resource.labels.service_name=tuki-celery-worker" \
    --format="value(timestamp,textPayload)" \
    2>&1 | grep -E --line-buffered "INFO|ERROR|WARNING|sync|SSH|Guardando|Verificación|Lock|Orden.*CREADA"

