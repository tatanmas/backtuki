#!/bin/bash

echo "🔍 Monitoreando sincronización en tiempo real..."
echo "Presiona Ctrl+C para salir"
echo ""

while true; do
    clear
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 MONITOR SINCRONIZACIÓN - $(date '+%H:%M:%S')"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # Backend - últimas tareas disparadas
    echo "🚀 BACKEND (últimos triggers):"
    gcloud logging read "resource.labels.service_name=tuki-backend AND textPayload=~\"disparadas\" AND timestamp>=\"$(date -u -v-5M +%Y-%m-%dT%H:%M:%SZ)\"" --limit=3 --format="value(timestamp.date('%H:%M:%S'),textPayload)" 2>/dev/null | head -3
    echo ""
    
    # Celery Worker - tareas recibidas
    echo "⚡ CELERY WORKER (tareas procesadas):"
    gcloud logging read "resource.labels.service_name=tuki-celery-worker AND (textPayload=~\"Received task\" OR textPayload=~\"sync_woocommerce_event\" OR textPayload=~\"SSH\" OR textPayload=~\"Iniciando sincronización\") AND timestamp>=\"$(date -u -v-5M +%Y-%m-%dT%H:%M:%SZ)\"" --limit=5 --format="value(timestamp.date('%H:%M:%S'),textPayload)" 2>/dev/null | head -5
    echo ""
    
    # Estado de conexión
    echo "🔗 ESTADO CELERY:"
    gcloud logging read "resource.labels.service_name=tuki-celery-worker AND (textPayload=~\"Connected to redis\" OR textPayload=~\"ready\" OR textPayload=~\"Starting\") AND timestamp>=\"$(date -u -v-2M +%Y-%m-%dT%H:%M:%SZ)\"" --limit=2 --format="value(timestamp.date('%H:%M:%S'),textPayload)" 2>/dev/null | head -2
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    sleep 3
done
