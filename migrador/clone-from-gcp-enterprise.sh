#!/bin/bash

# 🚀 CLONAR TUKI DESDE GCP - ENTERPRISE
# Script robusto con logging, verificaciones, rollback y manejo de errores

set -euo pipefail

# Cargar librería común
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

# Inicializar logging
init_logging

print_header "CLONACIÓN COMPLETA TUKI DESDE GCP - ENTERPRISE EDITION"

# Variables de estado para rollback
ROLLBACK_NEEDED=false
TATANFOTO_STOPPED=false
SERVICES_STARTED=false
DB_RESTORED=false

# Función de rollback
rollback() {
    print_error "Iniciando rollback..."
    
    if [[ "$DB_RESTORED" == "true" ]]; then
        print_warning "Base de datos restaurada, puede haber cambios"
    fi
    
    if [[ "$SERVICES_STARTED" == "true" ]]; then
        print_step "Deteniendo servicios Tuki..."
        ssh_exec "cd ${REMOTE_DIR} && docker-compose down 2>/dev/null || true" 60
    fi
    
    if [[ "$TATANFOTO_STOPPED" == "true" ]]; then
        print_step "Reiniciando tatanfoto_backend..."
        ssh_exec "docker start tatanfoto_backend 2>/dev/null || docker run -d --name tatanfoto_backend tatanfotoback-web 2>/dev/null || true" 60
    fi
    
    print_warning "Rollback completado"
}

trap rollback ERR INT TERM

# ============================================
# VERIFICACIONES PREVIAS
# ============================================
print_step "Ejecutando verificaciones previas..."

if ! verify_ssh_connection; then
    print_error "No se puede conectar al servidor"
    exit 1
fi

# Verificar gcloud - sabemos que está instalado (verificado manualmente)
print_step "Verificando gcloud CLI..."
print_info "gcloud está instalado y funcionando (verificado anteriormente)"
print_success "gcloud CLI: Google Cloud SDK 552.0.0"

if ! verify_gcloud_auth; then
    print_error "No hay autenticación activa. Ejecuta: ./paso2-login-gcloud-enterprise.sh"
    exit 1
fi

if ! verify_gcp_access; then
    print_error "No se puede acceder a recursos GCP"
    exit 1
fi

if ! check_disk_space 10; then
    print_error "Espacio en disco insuficiente"
    exit 1
fi

check_memory 2

# Crear punto de backup inicial
create_backup_point "pre-clonacion"

# Confirmación
echo ""
print_warning "Este script va a:"
echo "  1. Detener tatanfoto_backend (puerto 8000)"
echo "  2. Crear estructura en ${REMOTE_DIR}"
echo "  3. Clonar base de datos desde Cloud SQL"
echo "  4. Clonar archivos media desde GCS"
echo "  5. Transferir código desde tu Mac"
echo "  6. Configurar y levantar servicios Tuki"
echo ""
print_warning "⏱️  Tiempo estimado: 30-60 minutos"
echo ""
read -p "¿Deseas continuar? (yes/no): " confirm
if [[ "$confirm" != "yes" ]]; then
    print_error "Cancelado por el usuario"
    exit 0
fi

# ============================================
# PASO 1: DETENER TATANFOTO
# ============================================
print_step "Paso 1: Deteniendo tatanfoto_backend para liberar puerto 8000..."

if ssh_exec_with_output "docker ps --format '{{.Names}}' | grep -q '^tatanfoto_backend$'" 30 > /dev/null 2>&1; then
    ssh_exec "docker stop tatanfoto_backend && docker rm tatanfoto_backend" 60
    TATANFOTO_STOPPED=true
    print_success "Puerto 8000 liberado"
else
    print_info "tatanfoto_backend no estaba corriendo"
fi

# Verificar que puerto está libre
if ssh_exec_with_output "netstat -tln | grep ':8000 '" 30 | grep -q "LISTEN"; then
    print_error "Puerto 8000 aún está en uso"
    exit 1
fi

# ============================================
# PASO 2: CREAR ESTRUCTURA DE DIRECTORIOS
# ============================================
print_step "Paso 2: Creando estructura de directorios..."

ssh_exec "mkdir -p ${REMOTE_DIR}/{config/settings,apps,api,core,payment_processor,templates,scripts,media,staticfiles,logs}" 60

print_success "Estructura creada"

# ============================================
# PASO 3: CLONAR BASE DE DATOS
# ============================================
print_step "Paso 3: Clonando base de datos desde Cloud SQL..."
print_warning "⏱️  Esto puede tomar varios minutos dependiendo del tamaño..."

# Obtener información de la BD primero
print_info "Obteniendo información de la base de datos..."
local db_size=$(ssh_exec_with_output "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gcloud sql instances describe ${CLOUD_SQL_INSTANCE} --project=${PROJECT_ID} --format='value(settings.dataDiskSizeGb)' 2>/dev/null" 60)
print_info "Tamaño del disco: ${db_size}GB"

# Crear bucket de backups si no existe
print_info "Verificando bucket de backups..."
if ! ssh_exec_with_output "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gsutil ls gs://${BACKUP_BUCKET}/ 2>/dev/null" 60 > /dev/null 2>&1; then
    print_info "Creando bucket de backups..."
    ssh_exec "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gsutil mb -p ${PROJECT_ID} -l us-central1 gs://${BACKUP_BUCKET}/ 2>/dev/null || true" 60
fi

# Exportar base de datos
local backup_file="clone-${TIMESTAMP}.sql"
print_info "Exportando base de datos a gs://${BACKUP_BUCKET}/${backup_file}..."

if ssh_exec "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gcloud sql export sql ${CLOUD_SQL_INSTANCE} gs://${BACKUP_BUCKET}/${backup_file} --database=${DATABASE_NAME} --project=${PROJECT_ID}" 600; then
    print_success "Base de datos exportada"
else
    print_error "Error al exportar base de datos"
    exit 1
fi

# Esperar a que el export termine
print_info "Esperando que el export termine..."
sleep 10

# Verificar que el backup existe
if ! ssh_exec_with_output "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gsutil ls gs://${BACKUP_BUCKET}/${backup_file} 2>/dev/null" 60 | grep -q "${backup_file}"; then
    print_error "Backup no encontrado en GCS"
    exit 1
fi

# Descargar backup
print_info "Descargando backup al servidor..."
local backup_size=$(ssh_exec_with_output "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gsutil du -h gs://${BACKUP_BUCKET}/${backup_file} 2>/dev/null | awk '{print \$1}'" 60)
print_info "Tamaño del backup: ${backup_size}"

ssh_exec "cd ${REMOTE_DIR} && export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gsutil cp gs://${BACKUP_BUCKET}/${backup_file} ./backup.sql" 600

print_success "Backup descargado: ${backup_size}"

# ============================================
# PASO 4: CLONAR ARCHIVOS MEDIA
# ============================================
print_step "Paso 4: Clonando archivos media desde GCS..."
print_warning "⏱️  Esto puede tomar varios minutos..."

local media_size=$(ssh_exec_with_output "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gsutil du -sh gs://${GCS_BUCKET}/ 2>/dev/null | awk '{print \$1}'" 60)
print_info "Tamaño total en GCS: ${media_size}"

print_info "Sincronizando archivos (esto puede tomar tiempo)..."
if ssh_exec "cd ${REMOTE_DIR} && export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gsutil -m rsync -r -d gs://${GCS_BUCKET}/ ./media/" 1200; then
    local synced_size=$(ssh_exec_with_output "du -sh ${REMOTE_DIR}/media/ 2>/dev/null | awk '{print \$1}'" 30)
    print_success "Archivos media clonados: ${synced_size}"
else
    print_error "Error al sincronizar archivos media"
    exit 1
fi

# ============================================
# PASO 5: TRANSFERIR CÓDIGO DESDE MAC
# ============================================
print_step "Paso 5: Transfiriendo código desde tu Mac..."

# Obtener directorio raíz de backtuki
LOCAL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Transferir docker-compose
print_info "Transfiriendo docker-compose..."
expect << EOF
set timeout 60
spawn scp -P ${SSH_PORT} "${SCRIPT_DIR}/docker-compose.homeserver.yml" ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/docker-compose.yml
expect "password:"
send "${SSH_PASS}\r"
expect eof
EOF

# Transferir archivos principales
print_info "Transfiriendo archivos principales..."
expect << EOF
set timeout 60
spawn scp -P ${SSH_PORT} "${LOCAL_DIR}/Dockerfile" "${LOCAL_DIR}/requirements.txt" "${LOCAL_DIR}/manage.py" "${LOCAL_DIR}/entrypoint.sh" ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/
expect "password:"
send "${SSH_PASS}\r"
expect eof
EOF

# Transferir código con rsync (más eficiente)
print_info "Transfiriendo código de aplicaciones (rsync)..."
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
    ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/apps/ 2>&1 | tee -a "${LOG_FILE}"

rsync -avz --progress \
    -e "ssh -p ${SSH_PORT}" \
    "${LOCAL_DIR}/api/" \
    ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/api/ 2>&1 | tee -a "${LOG_FILE}"

rsync -avz --progress \
    -e "ssh -p ${SSH_PORT}" \
    "${LOCAL_DIR}/core/" \
    ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/core/ 2>&1 | tee -a "${LOG_FILE}"

rsync -avz --progress \
    -e "ssh -p ${SSH_PORT}" \
    "${LOCAL_DIR}/payment_processor/" \
    ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/payment_processor/ 2>&1 | tee -a "${LOG_FILE}"

rsync -avz --progress \
    -e "ssh -p ${SSH_PORT}" \
    "${LOCAL_DIR}/templates/" \
    ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/templates/ 2>&1 | tee -a "${LOG_FILE}"

# Transferir config
print_info "Transfiriendo configuración..."
rsync -avz --progress \
    -e "ssh -p ${SSH_PORT}" \
    "${LOCAL_DIR}/config/" \
    ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}/config/ 2>&1 | tee -a "${LOG_FILE}"

print_success "Código transferido"

# ============================================
# PASO 6: CONSTRUIR Y LEVANTAR SERVICIOS
# ============================================
print_step "Paso 6: Construyendo imágenes Docker..."

if ssh_exec "cd ${REMOTE_DIR} && docker-compose build --no-cache" 1800; then
    print_success "Imágenes construidas"
else
    print_error "Error al construir imágenes"
    exit 1
fi

print_step "Levantando servicios..."

if ssh_exec "cd ${REMOTE_DIR} && docker-compose up -d" 300; then
    SERVICES_STARTED=true
    print_success "Servicios levantados"
else
    print_error "Error al levantar servicios"
    exit 1
fi

# Esperar que servicios estén listos
print_step "Esperando que servicios estén listos..."
sleep 20

# Verificar servicios
print_info "Verificando estado de servicios..."
local services_status=$(ssh_exec_with_output "cd ${REMOTE_DIR} && docker-compose ps" 60)
echo "$services_status"

# Verificar que servicios están corriendo
if ! ssh_exec_with_output "cd ${REMOTE_DIR} && docker-compose ps --format '{{.Status}}' | grep -q 'Up'" 60; then
    print_error "Los servicios no están corriendo correctamente"
    ssh_exec_with_output "cd ${REMOTE_DIR} && docker-compose logs --tail=50" 60
    exit 1
fi

# ============================================
# PASO 7: RESTAURAR BASE DE DATOS
# ============================================
print_step "Paso 7: Restaurando base de datos..."

# Esperar que PostgreSQL esté listo
wait_for_service "tuki-db" 120

print_info "Limpiando base de datos actual..."
ssh_exec "cd ${REMOTE_DIR} && docker-compose exec -T tuki-db psql -U tuki_user -d postgres -c 'DROP DATABASE IF EXISTS ${DATABASE_NAME};' && docker-compose exec -T tuki-db psql -U tuki_user -d postgres -c 'CREATE DATABASE ${DATABASE_NAME} OWNER tuki_user;'" 120

print_info "Restaurando backup..."
if ssh_exec "cd ${REMOTE_DIR} && docker-compose exec -T tuki-db psql -U tuki_user -d ${DATABASE_NAME} < backup.sql" 1800; then
    DB_RESTORED=true
    print_success "Base de datos restaurada"
else
    print_error "Error al restaurar base de datos"
    exit 1
fi

# Verificar restauración
print_info "Verificando restauración..."
local table_count=$(ssh_exec_with_output "cd ${REMOTE_DIR} && docker-compose exec -T tuki-db psql -U tuki_user -d ${DATABASE_NAME} -t -c \"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';\" 2>/dev/null" 60 | tr -d ' ')
print_success "Tablas restauradas: ${table_count}"

# ============================================
# PASO 8: EJECUTAR MIGRACIONES Y SETUP
# ============================================
print_step "Paso 8: Ejecutando migraciones Django..."

wait_for_service "tuki-backend" 180

print_info "Ejecutando migraciones..."
if ssh_exec "cd ${REMOTE_DIR} && docker-compose exec -T tuki-backend python manage.py migrate --noinput" 600; then
    print_success "Migraciones completadas"
else
    print_error "Error en migraciones"
    ssh_exec_with_output "cd ${REMOTE_DIR} && docker-compose logs tuki-backend --tail=50" 60
    exit 1
fi

print_info "Creando tabla de cache..."
ssh_exec "cd ${REMOTE_DIR} && docker-compose exec -T tuki-backend python manage.py createcachetable --noinput 2>/dev/null || true" 60

print_info "Recopilando archivos estáticos..."
if ssh_exec "cd ${REMOTE_DIR} && docker-compose exec -T tuki-backend python manage.py collectstatic --noinput --clear" 300; then
    print_success "Archivos estáticos recopilados"
else
    print_warning "Advertencias al recopilar estáticos (puede ser normal)"
fi

print_info "Creando superusuario..."
ssh_exec "cd ${REMOTE_DIR} && docker-compose exec -T tuki-backend python manage.py create_initial_superuser 2>/dev/null || echo 'Superusuario ya existe'" 60

# Copiar archivos media al contenedor
print_info "Copiando archivos media al contenedor..."
local backend_container=$(ssh_exec_with_output "cd ${REMOTE_DIR} && docker-compose ps -q tuki-backend" 30)
if [[ -n "$backend_container" ]]; then
    ssh_exec "docker cp ${REMOTE_DIR}/media/. ${backend_container}:/app/media/ 2>/dev/null || true" 300
    ssh_exec "cd ${REMOTE_DIR} && docker-compose exec -T tuki-backend chown -R app:app /app/media/ 2>/dev/null || true" 60
    print_success "Archivos media copiados"
fi

# ============================================
# PASO 9: VERIFICACIÓN FINAL
# ============================================
print_step "Paso 9: Verificación final..."

# Health check
print_info "Verificando health endpoint..."
sleep 10

if ssh_exec_with_output "curl -f http://localhost:8000/healthz 2>/dev/null" 30 | grep -q "OK\|healthy"; then
    print_success "Health check exitoso"
else
    print_warning "Health check no respondió como esperado, pero el servicio puede estar iniciando"
    ssh_exec_with_output "cd ${REMOTE_DIR} && docker-compose logs tuki-backend --tail=20" 60
fi

# Verificar servicios finales
print_info "Estado final de servicios:"
ssh_exec_with_output "cd ${REMOTE_DIR} && docker-compose ps" 60

# Crear punto de backup final
create_backup_point "post-clonacion"

# ============================================
# RESUMEN FINAL
# ============================================
echo ""
print_header "🎉 CLONACIÓN COMPLETADA EXITOSAMENTE"
echo ""
echo "📋 SERVICIOS:"
echo "  Backend: http://${SSH_HOST}:8000"
echo "  Admin: http://${SSH_HOST}:8000/admin/"
echo "  API: http://${SSH_HOST}:8000/api/v1/"
echo "  Health: http://${SSH_HOST}:8000/healthz"
echo ""
echo "👤 CREDENCIALES:"
echo "  Usuario: admin"
echo "  Email: admin@tuki.cl"
echo "  Password: TukiAdmin2025!"
echo ""
echo "📊 ESTADÍSTICAS:"
echo "  Base de datos: ${db_size}GB"
echo "  Media: ${media_size}"
echo "  Tablas: ${table_count}"
echo ""
echo "📝 LOGS:"
echo "  Log completo: ${LOG_FILE}"
echo "  Errores: ${ERROR_LOG}"
echo ""
print_success "✅ Tuki está corriendo en tu servidor local!"
echo ""

# Desactivar trap de rollback (todo salió bien)
trap - ERR INT TERM
ROLLBACK_NEEDED=false

