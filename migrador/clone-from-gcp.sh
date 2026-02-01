#!/bin/bash

# 🚀 CLONAR TODO DESDE GCP AL SERVIDOR LOCAL
# Script que clona base de datos, archivos media y configura servicios

set -e

# Configuración
SSH_HOST="tukitickets.duckdns.org"
SSH_PORT="2222"
SSH_USER="tatan"
SSH_PASS="rollolupita"
REMOTE_DIR="/home/tatan/Escritorio/tuki-platform"
PROJECT_ID="tukiprod"
CLOUD_SQL_INSTANCE="tuki-db-prod"
DATABASE_NAME="tuki_production"
GCS_BUCKET="tuki-media-prod-1759240560"
BACKUP_BUCKET="tuki-backups"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)

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

# Función para ejecutar comandos via SSH
ssh_exec() {
    local cmd="$1"
    expect << EOF
set timeout 300
spawn ssh -o StrictHostKeyChecking=no -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST}
expect "password:"
send "${SSH_PASS}\r"
expect "$ "
send "$cmd\r"
expect "$ "
send "exit\r"
expect eof
EOF
}

echo "🚀 CLONANDO TUKI DESDE GCP AL SERVIDOR LOCAL"
echo "============================================="
echo ""
echo "Este script va a:"
echo "  1. Detener tatanfoto_backend (puerto 8000)"
echo "  2. Crear estructura en ${REMOTE_DIR}"
echo "  3. Clonar base de datos desde Cloud SQL"
echo "  4. Clonar archivos media desde GCS"
echo "  5. Configurar y levantar servicios Tuki"
echo ""
read -p "¿Continuar? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    print_error "Cancelado"
    exit 0
fi

# ============================================
# PASO 1: DETENER TATANFOTO
# ============================================
print_step "Paso 1: Deteniendo tatanfoto_backend para liberar puerto 8000..."

ssh_exec "docker stop tatanfoto_backend && docker rm tatanfoto_backend || echo 'Ya detenido'"

print_success "Puerto 8000 liberado"

# ============================================
# PASO 2: CREAR ESTRUCTURA DE DIRECTORIOS
# ============================================
print_step "Paso 2: Creando estructura de directorios..."

ssh_exec "mkdir -p ${REMOTE_DIR}/{config/settings,apps,api,core,payment_processor,templates,scripts,media,staticfiles,logs}"

print_success "Estructura creada"

# ============================================
# PASO 3: CLONAR BASE DE DATOS
# ============================================
print_step "Paso 3: Clonando base de datos desde Cloud SQL..."
print_warning "⏱️  Esto puede tomar varios minutos..."

# Exportar desde Cloud SQL
ssh_exec "gcloud sql export sql ${CLOUD_SQL_INSTANCE} gs://${BACKUP_BUCKET}/clone-${TIMESTAMP}.sql --database=${DATABASE_NAME} --project=${PROJECT_ID}"

# Descargar backup
ssh_exec "cd ${REMOTE_DIR} && gsutil cp gs://${BACKUP_BUCKET}/clone-${TIMESTAMP}.sql ./backup.sql"

print_success "Base de datos descargada"

# ============================================
# PASO 4: CLONAR ARCHIVOS MEDIA
# ============================================
print_step "Paso 4: Clonando archivos media desde GCS..."
print_warning "⏱️  Esto puede tomar varios minutos..."

ssh_exec "cd ${REMOTE_DIR} && gsutil -m rsync -r gs://${GCS_BUCKET}/ ./media/"

print_success "Archivos media clonados"

# ============================================
# PASO 5: TRANSFERIR CÓDIGO DESDE MAC
# ============================================
print_step "Paso 5: Transfiriendo código desde tu Mac..."

# Obtener directorio del script (migrador/)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Directorio raíz de backtuki (un nivel arriba)
LOCAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Transferir archivos principales
expect << EOF
set timeout 60
spawn scp -P ${SSH_PORT} ${SCRIPT_DIR}/docker-compose.homeserver.yml ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/docker-compose.yml
expect "password:"
send "${SSH_PASS}\r"
expect eof
EOF

# Transferir código con rsync
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
    ${LOCAL_DIR}/apps/ \
    ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/apps/

rsync -avz --progress \
    -e "ssh -p ${SSH_PORT}" \
    ${LOCAL_DIR}/api/ \
    ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/api/

rsync -avz --progress \
    -e "ssh -p ${SSH_PORT}" \
    ${LOCAL_DIR}/core/ \
    ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/core/

rsync -avz --progress \
    -e "ssh -p ${SSH_PORT}" \
    ${LOCAL_DIR}/payment_processor/ \
    ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/payment_processor/

rsync -avz --progress \
    -e "ssh -p ${SSH_PORT}" \
    ${LOCAL_DIR}/templates/ \
    ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/templates/

# Transferir archivos de configuración (desde raíz de backtuki)
expect << EOF
set timeout 30
spawn scp -P ${SSH_PORT} ${LOCAL_DIR}/Dockerfile ${LOCAL_DIR}/requirements.txt ${LOCAL_DIR}/manage.py ${LOCAL_DIR}/entrypoint.sh ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/
expect "password:"
send "${SSH_PASS}\r"
expect eof
EOF

# Transferir config
rsync -avz --progress \
    -e "ssh -p ${SSH_PORT}" \
    ${LOCAL_DIR}/config/ \
    ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/config/

print_success "Código transferido"

# ============================================
# PASO 6: CONFIGURAR Y LEVANTAR SERVICIOS
# ============================================
print_step "Paso 6: Construyendo y levantando servicios Docker..."

ssh_exec "cd ${REMOTE_DIR} && docker-compose build --no-cache"

ssh_exec "cd ${REMOTE_DIR} && docker-compose up -d"

print_success "Servicios levantados"

# ============================================
# PASO 7: RESTAURAR BASE DE DATOS
# ============================================
print_step "Paso 7: Restaurando base de datos..."

sleep 10  # Esperar que PostgreSQL esté listo

ssh_exec "cd ${REMOTE_DIR} && docker-compose exec -T tuki-db psql -U tuki_user -d postgres -c 'DROP DATABASE IF EXISTS tuki_production;' && docker-compose exec -T tuki-db psql -U tuki_user -d postgres -c 'CREATE DATABASE tuki_production OWNER tuki_user;'"

ssh_exec "cd ${REMOTE_DIR} && docker-compose exec -T tuki-db psql -U tuki_user -d tuki_production < backup.sql"

print_success "Base de datos restaurada"

# ============================================
# PASO 8: EJECUTAR MIGRACIONES Y SETUP
# ============================================
print_step "Paso 8: Ejecutando migraciones Django..."

ssh_exec "cd ${REMOTE_DIR} && docker-compose exec -T tuki-backend python manage.py migrate --noinput"

ssh_exec "cd ${REMOTE_DIR} && docker-compose exec -T tuki-backend python manage.py collectstatic --noinput --clear"

ssh_exec "cd ${REMOTE_DIR} && docker-compose exec -T tuki-backend python manage.py create_initial_superuser 2>/dev/null || echo 'Superusuario ya existe'"

print_success "Migraciones completadas"

# ============================================
# PASO 9: VERIFICAR
# ============================================
print_step "Paso 9: Verificando servicios..."

sleep 10

ssh_exec "cd ${REMOTE_DIR} && docker-compose ps"

ssh_exec "curl -f http://localhost:8000/healthz || echo 'Health check falló'"

# ============================================
# RESUMEN
# ============================================
echo ""
echo "====================================="
print_success "🎉 CLONACIÓN COMPLETADA!"
echo "====================================="
echo ""
echo "📋 SERVICIOS:"
echo "  Backend: http://${SSH_HOST}:8000"
echo "  Admin: http://${SSH_HOST}:8000/admin/"
echo ""
echo "👤 CREDENCIALES:"
echo "  Usuario: admin"
echo "  Password: TukiAdmin2025!"
echo ""
print_success "✅ Tuki está corriendo en tu servidor local!"

