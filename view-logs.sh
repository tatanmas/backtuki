#!/bin/bash

# 🔍 TUKI LOGS VIEWER - Ver logs en vivo de servicios Cloud Run
# Script interactivo para monitorear servicios en tiempo real

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}🔍 TUKI LOGS VIEWER - Monitoreo en tiempo real${NC}"
echo "=============================================="
echo ""

# Listar servicios disponibles
echo -e "${BLUE}📋 Servicios disponibles:${NC}"
echo ""
echo "1) tuki-backend         - API REST principal"
echo "2) tuki-celery-worker   - Worker de tareas asíncronas"
echo "3) tuki-celery-beat     - Scheduler de tareas"
echo "4) tuki-frontend        - Frontend React"
echo ""
echo -e "${YELLOW}Opciones especiales:${NC}"
echo "5) Ver TODOS los servicios en paralelo"
echo "6) Solo ERRORES de todos los servicios"
echo ""

# Leer selección
read -p "Selecciona un servicio (1-6): " choice

# Filtros opcionales
echo ""
echo -e "${BLUE}🔧 Filtros (opcional, presiona Enter para ver todo):${NC}"
read -p "Buscar texto específico (ej: SSH, Error, sync): " filter

# Función para ver logs
view_logs() {
    local service=$1
    local filter_text=$2
    
    echo ""
    echo -e "${GREEN}📡 Monitoreando: $service${NC}"
    echo -e "${YELLOW}Presiona Ctrl+C para detener${NC}"
    echo "=================================="
    echo ""
    
    if [ -z "$filter_text" ]; then
        # Sin filtro - ver todo
        gcloud logging tail "resource.labels.service_name=$service" \
            --format="table(timestamp,severity,textPayload)"
    else
        # Con filtro
        gcloud logging tail "resource.labels.service_name=$service" \
            --format="table(timestamp,severity,textPayload)" \
            | grep -i --line-buffered --color=auto "$filter_text"
    fi
}

# Procesar selección
case $choice in
    1)
        view_logs "tuki-backend" "$filter"
        ;;
    2)
        view_logs "tuki-celery-worker" "$filter"
        ;;
    3)
        view_logs "tuki-celery-beat" "$filter"
        ;;
    4)
        view_logs "tuki-frontend" "$filter"
        ;;
    5)
        echo -e "${GREEN}📡 Monitoreando TODOS los servicios${NC}"
        echo "=================================="
        echo ""
        gcloud logging tail "resource.type=cloud_run_revision" \
            --format="value(resource.labels.service_name,timestamp,severity,textPayload)" \
            2>&1 | while read line; do
                if [[ $line == tuki-* ]]; then
                    echo -e "${CYAN}[$line]${NC}"
                else
                    echo "$line"
                fi
            done
        ;;
    6)
        echo -e "${RED}📡 Monitoreando solo ERRORES${NC}"
        echo "=================================="
        echo ""
        gcloud logging tail "resource.type=cloud_run_revision AND severity>=ERROR" \
            --format="value(resource.labels.service_name,timestamp,textPayload)"
        ;;
    *)
        echo -e "${RED}❌ Opción inválida${NC}"
        exit 1
        ;;
esac

