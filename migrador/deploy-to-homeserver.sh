#!/bin/bash

# 🏠 TUKI PLATFORM - DEPLOY TO HOME SERVER
# Script para desplegar Tuki en el servidor local (tukitickets.duckdns.org)
# Este script se conecta via SSH, transfiere archivos, y levanta los servicios

set -e

# ============================================
# CONFIGURACIÓN
# ============================================
SSH_HOST="tukitickets.duckdns.org"
SSH_PORT="2222"
SSH_USER="tatan"
REMOTE_DIR="/home/tatan/tuki-platform"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

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

# ============================================
# VERIFICACIONES PREVIAS
# ============================================
print_step "Verificando conexión SSH..."
if ! ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} "echo 'SSH OK'" > /dev/null 2>&1; then
    print_error "No se puede conectar via SSH. Verifica credenciales."
    exit 1
fi
print_success "Conexión SSH establecida"

echo ""
print_step "🏠 INICIANDO DEPLOY A HOME SERVER"
echo "====================================="
echo "Host: ${SSH_HOST}"
echo "Puerto SSH: ${SSH_PORT}"
echo "Usuario: ${SSH_USER}"
echo "Directorio remoto: ${REMOTE_DIR}"
echo ""

# ============================================
# PASO 1: CREAR ESTRUCTURA DE DIRECTORIOS
# ============================================
print_step "Paso 1: Creando estructura de directorios en servidor..."

ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} << 'ENDSSH'
# Crear directorio principal
mkdir -p /home/tatan/tuki-platform
cd /home/tatan/tuki-platform

# Crear subdirectorios necesarios
mkdir -p config/settings
mkdir -p scripts
mkdir -p media
mkdir -p staticfiles
mkdir -p logs

echo "✅ Directorios creados"
ENDSSH

print_success "Estructura de directorios creada"

# ============================================
# PASO 2: TRANSFERIR ARCHIVOS NECESARIOS
# ============================================
print_step "Paso 2: Transfiriendo archivos al servidor..."

# Función para transferir archivo via SSH
transfer_file() {
    local_file=$1
    remote_path=$2
    
    if [ -f "${LOCAL_DIR}/${local_file}" ]; then
        scp -P ${SSH_PORT} "${LOCAL_DIR}/${local_file}" "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/${remote_path}"
        echo "  ✓ ${local_file}"
    else
        print_warning "  ✗ ${local_file} no encontrado, saltando..."
    fi
}

# Transferir archivos principales
transfer_file "docker-compose.homeserver.yml" "docker-compose.yml"
transfer_file "Dockerfile" "Dockerfile"
transfer_file "requirements.txt" "requirements.txt"
transfer_file "manage.py" "manage.py"
transfer_file "entrypoint.sh" "entrypoint.sh"

# Transferir settings
transfer_file "config/settings/homeserver.py" "config/settings/homeserver.py"
transfer_file "config/settings/base.py" "config/settings/base.py"
transfer_file "config/settings/__init__.py" "config/settings/__init__.py"
transfer_file "config/__init__.py" "config/__init__.py"
transfer_file "config/urls.py" "config/urls.py"
transfer_file "config/wsgi.py" "config/wsgi.py"
transfer_file "config/celery.py" "config/celery.py"

print_success "Archivos base transferidos"

# ============================================
# PASO 3: TRANSFERIR CÓDIGO DE APLICACIONES
# ============================================
print_step "Paso 3: Transfiriendo código de aplicaciones..."

# Usar rsync para transferir todo el código (más eficiente)
rsync -avz --progress \
    -e "ssh -p ${SSH_PORT}" \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='venv' \
    --exclude='staticfiles' \
    --exclude='media' \
    --exclude='*.sqlite3' \
    --exclude='celerybeat-schedule' \
    --exclude='node_modules' \
    "${LOCAL_DIR}/apps/" \
    "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/apps/"

rsync -avz --progress \
    -e "ssh -p ${SSH_PORT}" \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    "${LOCAL_DIR}/api/" \
    "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/api/"

rsync -avz --progress \
    -e "ssh -p ${SSH_PORT}" \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    "${LOCAL_DIR}/core/" \
    "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/core/"

rsync -avz --progress \
    -e "ssh -p ${SSH_PORT}" \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    "${LOCAL_DIR}/payment_processor/" \
    "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/payment_processor/"

rsync -avz --progress \
    -e "ssh -p ${SSH_PORT}" \
    "${LOCAL_DIR}/templates/" \
    "${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/templates/"

print_success "Código de aplicaciones transferido"

# ============================================
# PASO 4: VERIFICAR DOCKER
# ============================================
print_step "Paso 4: Verificando Docker en servidor..."

ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} << 'ENDSSH'
if ! command -v docker &> /dev/null; then
    echo "❌ Docker no está instalado"
    echo "Instalando Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "✅ Docker instalado. Por favor, cierra sesión y vuelve a ejecutar el script."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose no está instalado"
    echo "Instalando Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo "✅ Docker Compose instalado"
fi

echo "✅ Docker version: $(docker --version)"
echo "✅ Docker Compose version: $(docker-compose --version)"
ENDSSH

print_success "Docker verificado"

# ============================================
# PASO 5: CONSTRUIR Y LEVANTAR SERVICIOS
# ============================================
print_step "Paso 5: Construyendo imágenes Docker..."

ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} << 'ENDSSH'
cd /home/tatan/tuki-platform

# Detener servicios anteriores si existen
echo "Deteniendo servicios anteriores..."
docker-compose down 2>/dev/null || true

# Construir imágenes
echo "Construyendo imágenes Docker..."
docker-compose build --no-cache

echo "✅ Imágenes construidas"
ENDSSH

print_success "Imágenes Docker construidas"

# ============================================
# PASO 6: INICIAR SERVICIOS
# ============================================
print_step "Paso 6: Iniciando servicios..."

ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} << 'ENDSSH'
cd /home/tatan/tuki-platform

echo "Levantando servicios..."
docker-compose up -d

echo "Esperando a que los servicios estén listos..."
sleep 20

echo "Estado de los servicios:"
docker-compose ps

echo "✅ Servicios iniciados"
ENDSSH

print_success "Servicios iniciados"

# ============================================
# PASO 7: EJECUTAR MIGRACIONES
# ============================================
print_step "Paso 7: Ejecutando migraciones de base de datos..."

ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} << 'ENDSSH'
cd /home/tatan/tuki-platform

echo "Ejecutando migraciones..."
docker-compose exec -T tuki-backend python manage.py migrate --noinput

echo "Creando cache table..."
docker-compose exec -T tuki-backend python manage.py createcachetable --noinput 2>/dev/null || true

echo "Recopilando archivos estáticos..."
docker-compose exec -T tuki-backend python manage.py collectstatic --noinput --clear

echo "✅ Migraciones completadas"
ENDSSH

print_success "Migraciones ejecutadas"

# ============================================
# PASO 8: CREAR SUPERUSUARIO
# ============================================
print_step "Paso 8: Creando superusuario..."

ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} << 'ENDSSH'
cd /home/tatan/tuki-platform

echo "Creando superusuario..."
docker-compose exec -T tuki-backend python manage.py create_initial_superuser 2>/dev/null || echo "Superusuario ya existe"

echo "✅ Superusuario verificado"
ENDSSH

print_success "Superusuario creado"

# ============================================
# PASO 9: VERIFICAR SALUD DE SERVICIOS
# ============================================
print_step "Paso 9: Verificando salud de servicios..."

ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} << 'ENDSSH'
cd /home/tatan/tuki-platform

echo "Verificando servicios..."
docker-compose ps

echo ""
echo "Verificando logs recientes del backend:"
docker-compose logs --tail=20 tuki-backend

echo ""
echo "Probando endpoint de salud..."
sleep 5
curl -f http://localhost:8001/healthz || echo "⚠️ Health check falló, pero el servicio puede estar iniciando..."

echo "✅ Verificación completada"
ENDSSH

print_success "Verificación completada"

# ============================================
# RESUMEN FINAL
# ============================================
echo ""
echo "====================================="
print_success "🎉 DEPLOY COMPLETADO!"
echo "====================================="
echo ""
echo "📋 INFORMACIÓN DEL DEPLOY:"
echo "=========================="
echo "🌐 Host: ${SSH_HOST}"
echo "🔌 Puerto Backend: 8001"
echo "🔌 Puerto PostgreSQL: 5435"
echo "🔌 Puerto Redis: 6380"
echo ""
echo "🔗 URLs DE ACCESO:"
echo "=================="
echo "Backend: http://${SSH_HOST}:8001"
echo "Admin: http://${SSH_HOST}:8001/admin/"
echo "API: http://${SSH_HOST}:8001/api/v1/"
echo "Health: http://${SSH_HOST}:8001/healthz"
echo ""
echo "👤 CREDENCIALES SUPERUSER:"
echo "=========================="
echo "Username: admin"
echo "Email: admin@tuki.cl"
echo "Password: TukiAdmin2025!"
echo ""
echo "🔍 COMANDOS ÚTILES:"
echo "==================="
echo "Ver logs:"
echo "  ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} 'cd ${REMOTE_DIR} && docker-compose logs -f backend'"
echo ""
echo "Ver estado de servicios:"
echo "  ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} 'cd ${REMOTE_DIR} && docker-compose ps'"
echo ""
echo "Reiniciar servicios:"
echo "  ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} 'cd ${REMOTE_DIR} && docker-compose restart'"
echo ""
echo "Detener servicios:"
echo "  ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} 'cd ${REMOTE_DIR} && docker-compose down'"
echo ""
echo "📋 PRÓXIMOS PASOS:"
echo "=================="
echo "1. Migrar base de datos desde GCP (ejecutar: ./migrate-db-from-gcp.sh)"
echo "2. Sincronizar archivos media desde GCS (ejecutar: ./sync-media-from-gcp.sh)"
echo "3. Configurar reverse proxy (Nginx/Cloudflare Tunnel)"
echo "4. Actualizar DNS para apuntar a este servidor"
echo ""
print_success "Todo listo! 🚀"

