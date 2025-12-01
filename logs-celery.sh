#!/bin/bash
# Ver logs de Celery Worker en tiempo real usando polling continuo
# Alternativa a gcloud beta logging tail que puede fallar

FILTER="resource.type=cloud_run_revision AND resource.labels.service_name=tuki-celery-worker"
TEMP_FILE="/tmp/celery_timestamp_$$.txt"

# Limpiar al salir
trap "rm -f $TEMP_FILE" EXIT

echo "🔍 Celery Worker - Logs en vivo (Ctrl+C para salir)"
echo "=================================================="
echo ""

# Obtener timestamp inicial (hace 5 segundos)
if [[ "$OSTYPE" == "darwin"* ]]; then
    LAST_TIMESTAMP=$(date -u -v-5S '+%Y-%m-%dT%H:%M:%SZ')
else
    LAST_TIMESTAMP=$(date -u -d '5 seconds ago' '+%Y-%m-%dT%H:%M:%SZ')
fi

while true; do
    # Obtener logs desde el último timestamp
    QUERY="$FILTER AND timestamp>=\"$LAST_TIMESTAMP\""
    
    # Leer logs y procesar
    gcloud logging read "$QUERY" \
        --limit=500 \
        --format="value(timestamp,textPayload)" \
        --freshness=1m \
        2>/dev/null | while IFS=$'\t' read -r timestamp payload; do
        if [ -n "$timestamp" ] && [ -n "$payload" ]; then
            # Mostrar log
            echo "[$timestamp] $payload"
            # Guardar timestamp más reciente
            if [[ "$timestamp" > "$LAST_TIMESTAMP" ]]; then
                echo "$timestamp" > "$TEMP_FILE"
            fi
        fi
    done
    
    # Actualizar último timestamp desde archivo temporal
    if [ -f "$TEMP_FILE" ] && [ -s "$TEMP_FILE" ]; then
        LAST_TIMESTAMP=$(cat "$TEMP_FILE")
    fi
    
    # Esperar 1 segundo antes de la siguiente consulta
    sleep 1
done
