#!/bin/bash

# 🔍 TUKI LIVE LOGS - Ver logs actualizándose

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

clear
echo -e "${CYAN}╔════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   🔍 TUKI LOGS - En Vivo                  ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}📋 Servicios:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1) 🖥️  tuki-backend"
echo "2) 🖥️  tuki-backend-prod"
echo "3) ⚙️  tuki-celery-beat"
echo "4) ⚙️  tuki-celery-worker"
echo "5) 🎨 tuki-frontend"
echo "6) 🎨 tuki-frontend-prod"
echo ""
read -p "Servicio (1-6): " choice

case $choice in
    1) SVC="tuki-backend" ;;
    2) SVC="tuki-backend-prod" ;;
    3) SVC="tuki-celery-beat" ;;
    4) SVC="tuki-celery-worker" ;;
    5) SVC="tuki-frontend" ;;
    6) SVC="tuki-frontend-prod" ;;
    *) echo -e "${RED}❌ Inválido${NC}"; exit 1 ;;
esac

echo ""
echo -e "${GREEN}✅ ${SVC}${NC}"
echo ""
echo "1) Todos los logs"
echo "2) Solo errores"  
echo "3) Filtrar texto"
echo ""
read -p "Opción (1-3): " opt

FILTER=""
if [ "$opt" = "3" ]; then
    read -p "Buscar: " FILTER
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📡 ${SVC} - Ctrl+C para salir${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Función para obtener logs
get_logs() {
    if [ "$opt" = "2" ]; then
        gcloud logging read "resource.labels.service_name=$SVC AND severity>=ERROR" \
            --limit=30 --format="value(timestamp.date('%H:%M:%S'),textPayload)" 2>/dev/null
    elif [ -n "$FILTER" ]; then
        gcloud logging read "resource.labels.service_name=$SVC" \
            --limit=100 --format="value(timestamp.date('%H:%M:%S'),textPayload)" 2>/dev/null \
            | grep -i --color=always "$FILTER"
    else
        gcloud logging read "resource.labels.service_name=$SVC" \
            --limit=40 --format="value(timestamp.date('%H:%M:%S'),textPayload)" 2>/dev/null
    fi
}

# Loop de actualización
LAST_HASH=""
while true; do
    CURRENT=$(get_logs)
    CURRENT_HASH=$(echo "$CURRENT" | md5)
    
    # Solo actualizar si cambió
    if [ "$CURRENT_HASH" != "$LAST_HASH" ]; then
        clear
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${GREEN}📡 ${SVC} - $(date '+%H:%M:%S')${NC}"
        if [ -n "$FILTER" ]; then
            echo -e "${BLUE}🔍 Filtro: '$FILTER'${NC}"
        fi
        echo -e "${YELLOW}Ctrl+C para salir - Actualiza cada 3s${NC}"
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        echo "$CURRENT"
        LAST_HASH="$CURRENT_HASH"
    fi
    
    sleep 3
done
