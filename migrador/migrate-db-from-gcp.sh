#!/bin/bash

# 📊 MIGRATE DATABASE FROM GCP TO HOME SERVER
# Este script exporta la base de datos desde Cloud SQL y la importa en el servidor local

set -e

# ============================================
# CONFIGURACIÓN
# ============================================
PROJECT_ID="tukiprod"
CLOUD_SQL_INSTANCE="tuki-db-prod"
DATABASE_NAME="tuki_production"
BUCKET_NAME="tuki-backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="migration-${TIMESTAMP}.sql"

SSH_HOST="tukitickets.duckdns.org"
SSH_PORT="2222"
SSH_USER="tatan"
REMOTE_DIR="/home/tatan/tuki-platform"

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

echo "📊 MIGRANDO BASE DE DATOS GCP → HOME SERVER"
echo "============================================="
echo ""

# ============================================
# PASO 1: CREAR BUCKET DE BACKUPS SI NO EXISTE
# ============================================
print_step "Paso 1: Verificando bucket de backups..."

if ! gsutil ls gs://${BUCKET_NAME} &>/dev/null; then
    print_warning "Bucket no existe, creando..."
    gsutil mb -p ${PROJECT_ID} -l us-central1 gs://${BUCKET_NAME}
    print_success "Bucket creado"
else
    print_success "Bucket existe"
fi

# ============================================
# PASO 2: EXPORTAR BASE DE DATOS DESDE CLOUD SQL
# ============================================
print_step "Paso 2: Exportando base de datos desde Cloud SQL..."
print_warning "⏱️  Esto puede tomar varios minutos dependiendo del tamaño de la BD..."

gcloud sql export sql ${CLOUD_SQL_INSTANCE} \
    gs://${BUCKET_NAME}/${BACKUP_FILE} \
    --database=${DATABASE_NAME} \
    --project=${PROJECT_ID}

if [ $? -eq 0 ]; then
    print_success "Base de datos exportada a gs://${BUCKET_NAME}/${BACKUP_FILE}"
else
    print_error "Error al exportar base de datos"
    exit 1
fi

# Verificar tamaño del backup
BACKUP_SIZE=$(gsutil du -h gs://${BUCKET_NAME}/${BACKUP_FILE} | awk '{print $1}')
print_success "Tamaño del backup: ${BACKUP_SIZE}"

# ============================================
# PASO 3: DESCARGAR BACKUP LOCALMENTE
# ============================================
print_step "Paso 3: Descargando backup..."

TEMP_DIR="/tmp/tuki-migration-${TIMESTAMP}"
mkdir -p ${TEMP_DIR}

gsutil cp gs://${BUCKET_NAME}/${BACKUP_FILE} ${TEMP_DIR}/

if [ $? -eq 0 ]; then
    print_success "Backup descargado a ${TEMP_DIR}/${BACKUP_FILE}"
else
    print_error "Error al descargar backup"
    exit 1
fi

# ============================================
# PASO 4: TRANSFERIR BACKUP AL SERVIDOR LOCAL
# ============================================
print_step "Paso 4: Transfiriendo backup al servidor local..."
print_warning "⏱️  Esto puede tomar varios minutos dependiendo de tu conexión..."

scp -P ${SSH_PORT} \
    ${TEMP_DIR}/${BACKUP_FILE} \
    ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/backup.sql

if [ $? -eq 0 ]; then
    print_success "Backup transferido al servidor local"
else
    print_error "Error al transferir backup"
    exit 1
fi

# ============================================
# PASO 5: IMPORTAR EN POSTGRESQL LOCAL
# ============================================
print_step "Paso 5: Importando base de datos en servidor local..."
print_warning "⏱️  Esto puede tomar varios minutos..."

ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} << ENDSSH
cd ${REMOTE_DIR}

echo "Verificando que la base de datos esté lista..."
docker-compose exec -T tuki-db pg_isready -U tuki_user -d tuki_production

echo "Limpiando base de datos actual (si existe)..."
docker-compose exec -T tuki-db psql -U tuki_user -d postgres -c "DROP DATABASE IF EXISTS tuki_production;"
docker-compose exec -T tuki-db psql -U tuki_user -d postgres -c "CREATE DATABASE tuki_production OWNER tuki_user;"

echo "Importando backup..."
docker-compose exec -T tuki-db psql -U tuki_user -d tuki_production < backup.sql

if [ \$? -eq 0 ]; then
    echo "✅ Base de datos importada exitosamente"
else
    echo "❌ Error al importar base de datos"
    exit 1
fi

echo "Verificando importación..."
docker-compose exec -T tuki-db psql -U tuki_user -d tuki_production -c "SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema = 'public';"

echo "Reiniciando backend para aplicar cambios..."
docker-compose restart tuki-backend celery-worker celery-beat

echo "✅ Importación completada"
ENDSSH

if [ $? -eq 0 ]; then
    print_success "Base de datos importada en servidor local"
else
    print_error "Error al importar base de datos"
    exit 1
fi

# ============================================
# PASO 6: LIMPIAR ARCHIVOS TEMPORALES
# ============================================
print_step "Paso 6: Limpiando archivos temporales..."

rm -rf ${TEMP_DIR}
ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} "rm -f ${REMOTE_DIR}/backup.sql"

print_success "Archivos temporales eliminados"

# ============================================
# PASO 7: VERIFICAR MIGRACIÓN
# ============================================
print_step "Paso 7: Verificando migración..."

ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} << 'ENDSSH'
cd /home/tatan/tuki-platform

echo "Probando conexión a la base de datos..."
docker-compose exec -T tuki-backend python manage.py check --database default

echo "Verificando migraciones..."
docker-compose exec -T tuki-backend python manage.py showmigrations

echo "✅ Verificación completada"
ENDSSH

if [ $? -eq 0 ]; then
    print_success "Verificación exitosa"
else
    print_warning "Verificación con warnings, revisar logs"
fi

# ============================================
# RESUMEN FINAL
# ============================================
echo ""
echo "====================================="
print_success "🎉 MIGRACIÓN DE BASE DE DATOS COMPLETADA!"
echo "====================================="
echo ""
echo "📊 RESUMEN:"
echo "==========="
echo "Origen: Cloud SQL (${CLOUD_SQL_INSTANCE})"
echo "Destino: Home Server PostgreSQL (puerto 5435)"
echo "Backup: gs://${BUCKET_NAME}/${BACKUP_FILE}"
echo "Tamaño: ${BACKUP_SIZE}"
echo ""
echo "🔍 VERIFICACIÓN:"
echo "================"
echo "Para verificar que todo funcionó:"
echo "  ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST}"
echo "  cd ${REMOTE_DIR}"
echo "  docker-compose exec tuki-db psql -U tuki_user -d tuki_production"
echo ""
echo "📋 PRÓXIMOS PASOS:"
echo "=================="
echo "1. ✅ Base de datos migrada"
echo "2. ⏳ Migrar archivos media (ejecutar: ./sync-media-from-gcp.sh)"
echo "3. ⏳ Configurar DNS/reverse proxy"
echo "4. ⏳ Verificar funcionamiento completo"
echo ""
print_success "Migración exitosa! 🚀"

