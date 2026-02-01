#!/bin/bash

# 🚀 FULL MIGRATION: GCP → HOME SERVER
# Script maestro que ejecuta toda la migración en orden

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m'

print_header() { echo -e "${MAGENTA}$1${NC}"; }
print_step() { echo -e "${BLUE}🔧 $1${NC}"; }
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }

clear
print_header "╔════════════════════════════════════════════════════════════╗"
print_header "║                                                            ║"
print_header "║        🚀 TUKI PLATFORM - MIGRACIÓN COMPLETA 🚀           ║"
print_header "║                                                            ║"
print_header "║            GCP → HOME SERVER (AUTOMATIZADA)                ║"
print_header "║                                                            ║"
print_header "╚════════════════════════════════════════════════════════════╝"
echo ""

print_warning "Esta migración incluye:"
echo "  1. Despliegue de infraestructura en servidor local"
echo "  2. Migración de base de datos desde Cloud SQL"
echo "  3. Sincronización de archivos media desde GCS"
echo "  4. Verificación de funcionamiento"
echo ""
print_warning "⏱️  Tiempo estimado: 30-60 minutos"
print_warning "💾 Espacio requerido: ~5GB"
echo ""

# Pedir confirmación
read -p "¿Deseas continuar? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    print_error "Migración cancelada"
    exit 0
fi

echo ""
print_success "¡Iniciando migración!"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/migration-$(date +%Y%m%d-%H%M%S).log"

print_step "Los logs se guardarán en: ${LOG_FILE}"
echo ""

# Función para ejecutar paso con logging
run_step() {
    step_num=$1
    step_name=$2
    script_path=$3
    
    print_header "═══════════════════════════════════════════════════════════"
    print_header "   PASO ${step_num}: ${step_name}"
    print_header "═══════════════════════════════════════════════════════════"
    echo ""
    
    if [ -f "${script_path}" ]; then
        bash "${script_path}" 2>&1 | tee -a "${LOG_FILE}"
        
        if [ ${PIPESTATUS[0]} -eq 0 ]; then
            echo ""
            print_success "✅ Paso ${step_num} completado exitosamente"
            echo ""
            sleep 2
        else
            echo ""
            print_error "❌ Error en paso ${step_num}"
            print_error "Revisa los logs en: ${LOG_FILE}"
            echo ""
            print_warning "¿Deseas continuar de todas formas? (yes/no)"
            read -p "> " continue_anyway
            if [ "$continue_anyway" != "yes" ]; then
                print_error "Migración abortada"
                exit 1
            fi
        fi
    else
        print_error "Script no encontrado: ${script_path}"
        exit 1
    fi
}

# ============================================
# EJECUTAR PASOS DE MIGRACIÓN
# ============================================

START_TIME=$(date +%s)

# PASO 1: Desplegar infraestructura
run_step "1" "DESPLEGAR INFRAESTRUCTURA EN HOME SERVER" \
    "${SCRIPT_DIR}/deploy-to-homeserver.sh"

# PASO 2: Migrar base de datos
run_step "2" "MIGRAR BASE DE DATOS DESDE CLOUD SQL" \
    "${SCRIPT_DIR}/migrate-db-from-gcp.sh"

# PASO 3: Sincronizar archivos media
run_step "3" "SINCRONIZAR ARCHIVOS MEDIA DESDE GCS" \
    "${SCRIPT_DIR}/sync-media-from-gcp.sh"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))

# ============================================
# RESUMEN FINAL
# ============================================

clear
print_header "╔════════════════════════════════════════════════════════════╗"
print_header "║                                                            ║"
print_header "║        🎉 MIGRACIÓN COMPLETADA EXITOSAMENTE! 🎉           ║"
print_header "║                                                            ║"
print_header "╚════════════════════════════════════════════════════════════╝"
echo ""

print_success "✅ Todos los pasos completados"
echo ""
echo "⏱️  Tiempo total: ${MINUTES}m ${SECONDS}s"
echo "📝 Logs guardados en: ${LOG_FILE}"
echo ""

print_header "═══════════════════════════════════════════════════════════"
print_header "   📋 RESUMEN DE SERVICIOS"
print_header "═══════════════════════════════════════════════════════════"
echo ""
echo "🏠 SERVIDOR LOCAL (tukitickets.duckdns.org)"
echo "  ├─ Backend:     http://tukitickets.duckdns.org:8001"
echo "  ├─ Admin:       http://tukitickets.duckdns.org:8001/admin/"
echo "  ├─ API:         http://tukitickets.duckdns.org:8001/api/v1/"
echo "  ├─ PostgreSQL:  puerto 5435"
echo "  └─ Redis:       puerto 6380"
echo ""
echo "👤 CREDENCIALES:"
echo "  ├─ Usuario:     admin"
echo "  ├─ Email:       admin@tuki.cl"
echo "  └─ Password:    TukiAdmin2025!"
echo ""

print_header "═══════════════════════════════════════════════════════════"
print_header "   🔍 VERIFICACIÓN MANUAL"
print_header "═══════════════════════════════════════════════════════════"
echo ""
echo "Por favor verifica manualmente:"
echo ""
echo "1. Acceder al admin panel:"
echo "   http://tukitickets.duckdns.org:8001/admin/"
echo ""
echo "2. Verificar que puedes:"
echo "   ├─ Ver eventos existentes"
echo "   ├─ Ver órdenes de compra"
echo "   ├─ Ver usuarios"
echo "   └─ Acceder a las imágenes de eventos"
echo ""
echo "3. Probar funcionalidades:"
echo "   ├─ Crear un evento de prueba"
echo "   ├─ Subir una imagen"
echo "   └─ Verificar que se guarde correctamente"
echo ""

print_header "═══════════════════════════════════════════════════════════"
print_header "   📋 PRÓXIMOS PASOS"
print_header "═══════════════════════════════════════════════════════════"
echo ""
echo "1. ✅ Infraestructura desplegada"
echo "2. ✅ Base de datos migrada"
echo "3. ✅ Archivos media sincronizados"
echo ""
echo "PENDIENTE:"
echo ""
echo "4. ⏳ Configurar reverse proxy (Nginx o Cloudflare Tunnel)"
echo "   └─ Para servir en puerto 80/443 con SSL"
echo ""
echo "5. ⏳ Actualizar DNS"
echo "   └─ Apuntar prop.cl a tukitickets.duckdns.org"
echo ""
echo "6. ⏳ Apagar servicios GCP (para ahorro de costos)"
echo "   └─ Ejecutar: gcloud run services update tuki-backend --min-instances=0"
echo ""
echo "7. ⏳ Configurar backups automáticos"
echo "   └─ Backup diario de PostgreSQL a GCS"
echo ""

print_header "═══════════════════════════════════════════════════════════"
print_header "   🛠️  COMANDOS ÚTILES"
print_header "═══════════════════════════════════════════════════════════"
echo ""
echo "Ver logs en tiempo real:"
echo "  ssh -p 2222 tatan@tukitickets.duckdns.org"
echo "  cd /home/tatan/tuki-platform"
echo "  docker-compose logs -f backend"
echo ""
echo "Ver estado de servicios:"
echo "  docker-compose ps"
echo ""
echo "Reiniciar servicios:"
echo "  docker-compose restart"
echo ""
echo "Detener servicios:"
echo "  docker-compose down"
echo ""
echo "Ver base de datos:"
echo "  docker-compose exec tuki-db psql -U tuki_user -d tuki_production"
echo ""

print_success "🎉 ¡Migración completada exitosamente!"
echo ""
print_warning "💡 TIP: Guarda este log para referencia futura"
echo "    Ubicación: ${LOG_FILE}"
echo ""

