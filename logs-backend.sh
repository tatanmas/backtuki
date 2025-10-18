#!/bin/bash
# Ver logs del Backend en tiempo real
echo "🔍 Backend - Logs en vivo (Ctrl+C para salir)"
echo "=============================================="
gcloud logging tail "resource.labels.service_name=tuki-backend" \
    --format="value(timestamp,severity,textPayload)" \
    2>&1 | grep -E --line-buffered "ERROR|sync|trigger|disparadas|POST|GET"

