#!/bin/bash
# Ver solo ERRORES de todos los servicios
echo "🚨 ERRORES - Todos los servicios (Ctrl+C para salir)"
echo "===================================================="
gcloud logging tail "resource.type=cloud_run_revision AND severity>=ERROR" \
    --format="value(resource.labels.service_name,timestamp,textPayload)"

