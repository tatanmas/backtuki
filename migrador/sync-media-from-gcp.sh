#!/bin/bash

# 📁 SYNC MEDIA FILES FROM GCS TO HOME SERVER
# Este script sincroniza todos los archivos media desde Google Cloud Storage al servidor local

set -e

# ============================================
# CONFIGURACIÓN
# ============================================
GCS_BUCKET="gs://tuki-media-prod-1759240560"
SSH_HOST="tukitickets.duckdns.org"
SSH_PORT="2222"
SSH_USER="tatan"
REMOTE_DIR="/home/tatan/tuki-platform"
TEMP_DIR="/tmp/tuki-media-sync"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_step() { echo -e "${BLUE}🔧 $1${NC}"; }
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }

echo "📁 SINCRONIZANDO ARCHIVOS MEDIA GCS → HOME SERVER"
echo "=================================================="
echo ""

# ============================================
# PASO 1: VERIFICAR TAMAÑO DE ARCHIVOS EN GCS
# ============================================
print_step "Paso 1: Analizando archivos en Google Cloud Storage..."

TOTAL_SIZE=$(gsutil du -sh ${GCS_BUCKET} | awk '{print $1}')
FILE_COUNT=$(gsutil ls -r ${GCS_BUCKET}/** 2>/dev/null | wc -l)

print_success "Total en GCS: ${TOTAL_SIZE} (${FILE_COUNT} archivos)"
print_warning "⏱️  La descarga puede tomar tiempo dependiendo del tamaño y tu conexión"

# ============================================
# PASO 2: DESCARGAR ARCHIVOS LOCALMENTE
# ============================================
print_step "Paso 2: Descargando archivos desde GCS..."

mkdir -p ${TEMP_DIR}

# Usar gsutil rsync para sincronización eficiente
gsutil -m rsync -r -d ${GCS_BUCKET}/ ${TEMP_DIR}/

if [ $? -eq 0 ]; then
    DOWNLOADED_SIZE=$(du -sh ${TEMP_DIR} | awk '{print $1}')
    print_success "Archivos descargados: ${DOWNLOADED_SIZE}"
else
    print_error "Error al descargar archivos desde GCS"
    exit 1
fi

# ============================================
# PASO 3: TRANSFERIR AL SERVIDOR LOCAL
# ============================================
print_step "Paso 3: Transfiriendo archivos al servidor local..."
print_warning "⏱️  Esto puede tomar varios minutos..."

# Crear directorio media en servidor si no existe
ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} \
    "mkdir -p ${REMOTE_DIR}/media"

# Usar rsync para transferencia eficiente con progreso
rsync -avz --progress \
    -e "ssh -p ${SSH_PORT}" \
    ${TEMP_DIR}/ \
    ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/media/

if [ $? -eq 0 ]; then
    print_success "Archivos transferidos al servidor local"
else
    print_error "Error al transferir archivos"
    exit 1
fi

# ============================================
# PASO 4: COPIAR ARCHIVOS AL VOLUMEN DOCKER
# ============================================
print_step "Paso 4: Copiando archivos al volumen Docker..."

ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} << ENDSSH
cd ${REMOTE_DIR}

echo "Verificando contenedor backend..."
if ! docker-compose ps tuki-backend | grep -q "Up"; then
    echo "❌ Contenedor backend no está corriendo"
    echo "Ejecuta primero: ./deploy-to-homeserver.sh"
    exit 1
fi

echo "Copiando archivos al contenedor..."
docker cp media/. \$(docker-compose ps -q tuki-backend):/app/media/

echo "Verificando permisos..."
docker-compose exec -T tuki-backend chown -R app:app /app/media/

echo "Verificando archivos copiados..."
FILE_COUNT=\$(docker-compose exec -T tuki-backend find /app/media -type f | wc -l)
echo "Total de archivos en contenedor: \${FILE_COUNT}"

echo "✅ Archivos copiados al volumen Docker"
ENDSSH

if [ $? -eq 0 ]; then
    print_success "Archivos copiados al volumen Docker"
else
    print_error "Error al copiar archivos al volumen"
    exit 1
fi

# ============================================
# PASO 5: VERIFICAR SINCRONIZACIÓN
# ============================================
print_step "Paso 5: Verificando sincronización..."

ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} << 'ENDSSH'
cd /home/tatan/tuki-platform

echo "Archivos en el servidor:"
du -sh media/

echo ""
echo "Archivos en el contenedor:"
docker-compose exec -T tuki-backend du -sh /app/media/

echo ""
echo "Ejemplos de archivos:"
docker-compose exec -T tuki-backend ls -lah /app/media/ | head -10

echo "✅ Verificación completada"
ENDSSH

if [ $? -eq 0 ]; then
    print_success "Verificación exitosa"
else
    print_warning "Verificación con warnings"
fi

# ============================================
# PASO 6: LIMPIAR ARCHIVOS TEMPORALES
# ============================================
print_step "Paso 6: Limpiando archivos temporales..."

rm -rf ${TEMP_DIR}

print_success "Archivos temporales eliminados"

# ============================================
# PASO 7: REINICIAR SERVICIOS
# ============================================
print_step "Paso 7: Reiniciando servicios para aplicar cambios..."

ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} << 'ENDSSH'
cd /home/tatan/tuki-platform

docker-compose restart tuki-backend

echo "Esperando que el servicio esté listo..."
sleep 10

echo "✅ Servicios reiniciados"
ENDSSH

print_success "Servicios reiniciados"

# ============================================
# RESUMEN FINAL
# ============================================
echo ""
echo "====================================="
print_success "🎉 SINCRONIZACIÓN DE MEDIA COMPLETADA!"
echo "====================================="
echo ""
echo "📁 RESUMEN:"
echo "==========="
echo "Origen: ${GCS_BUCKET}"
echo "Destino: ${SSH_HOST}:${REMOTE_DIR}/media/"
echo "Tamaño: ${TOTAL_SIZE}"
echo "Archivos: ${FILE_COUNT}"
echo ""
echo "🔍 VERIFICACIÓN:"
echo "================"
echo "Para verificar archivos en el contenedor:"
echo "  ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST}"
echo "  cd ${REMOTE_DIR}"
echo "  docker-compose exec tuki-backend ls -lah /app/media/"
echo ""
echo "Para probar carga de archivos:"
echo "  curl http://${SSH_HOST}:8001/media/[archivo]"
echo ""
echo "📋 PRÓXIMOS PASOS:"
echo "=================="
echo "1. ✅ Base de datos migrada"
echo "2. ✅ Archivos media sincronizados"
echo "3. ⏳ Configurar reverse proxy (Nginx/Cloudflare Tunnel)"
echo "4. ⏳ Actualizar DNS"
echo "5. ⏳ Verificar funcionamiento completo"
echo ""
print_success "Sincronización exitosa! 🚀"

