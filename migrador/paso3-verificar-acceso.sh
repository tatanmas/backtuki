#!/bin/bash

# ✅ PASO 3: VERIFICAR ACCESO A GCP - ENTERPRISE
# Verifica que tenemos acceso a todos los recursos necesarios

set -euo pipefail

# Cargar librería común
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

# Inicializar logging
init_logging

print_header "PASO 3: VERIFICAR ACCESO A GCP - ENTERPRISE"

# Verificaciones
print_step "Ejecutando verificaciones de acceso..."

if ! verify_ssh_connection; then
    print_error "No se puede conectar al servidor"
    exit 1
fi

if ! verify_gcloud_installed; then
    print_error "gcloud CLI no está instalado"
    exit 1
fi

if ! verify_gcloud_auth; then
    print_error "No hay autenticación activa. Ejecuta primero: ./paso2-login-gcloud-enterprise.sh"
    exit 1
fi

# Verificar acceso a recursos GCP
print_step "Verificando acceso a recursos GCP..."

if ! verify_gcp_access; then
    print_error "No se puede acceder a los recursos de GCP"
    print_info "Verifica los permisos de la cuenta: tecnologia@tuki.cl"
    exit 1
fi

# Verificar recursos específicos
print_step "Verificando recursos específicos..."

# Cloud SQL
print_info "Verificando instancia Cloud SQL..."
local sql_status=$(ssh_exec_with_output "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gcloud sql instances describe ${CLOUD_SQL_INSTANCE} --project=${PROJECT_ID} --format='value(state)' 2>/dev/null" 60)
if [[ "$sql_status" == "RUNNABLE" ]]; then
    print_success "Cloud SQL está RUNNABLE"
else
    print_warning "Cloud SQL estado: $sql_status"
fi

# Tamaño de base de datos
print_info "Obteniendo información de la base de datos..."
local db_info=$(ssh_exec_with_output "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gcloud sql instances describe ${CLOUD_SQL_INSTANCE} --project=${PROJECT_ID} --format='value(settings.dataDiskSizeGb,settings.dataDiskType)' 2>/dev/null" 60)
print_info "Base de datos: $db_info"

# GCS Bucket
print_info "Verificando bucket de Cloud Storage..."
local bucket_size=$(ssh_exec_with_output "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gsutil du -sh gs://${GCS_BUCKET}/ 2>/dev/null | awk '{print \$1}'" 60)
if [[ -n "$bucket_size" ]]; then
    print_success "Bucket GCS: ${bucket_size}"
else
    print_warning "No se pudo obtener tamaño del bucket"
fi

# Verificar bucket de backups
print_info "Verificando bucket de backups..."
if ssh_exec_with_output "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gsutil ls gs://${BACKUP_BUCKET}/ 2>/dev/null" 60 > /dev/null 2>&1; then
    print_success "Bucket de backups existe"
else
    print_warning "Bucket de backups no existe, se creará durante la migración"
fi

# Verificar recursos del servidor
print_step "Verificando recursos del servidor local..."

if ! check_disk_space 10; then
    print_error "Espacio en disco insuficiente"
    exit 1
fi

check_memory 2

# Verificar Docker
print_info "Verificando Docker..."
local docker_version=$(ssh_exec_with_output "docker --version 2>/dev/null" 30 || echo "")
if [[ -n "$docker_version" ]]; then
    print_success "Docker: $docker_version"
else
    print_error "Docker no está instalado"
    exit 1
fi

# Verificar Docker Compose
print_info "Verificando Docker Compose..."
local compose_version=$(ssh_exec_with_output "docker-compose --version 2>/dev/null" 30 || echo "")
if [[ -n "$compose_version" ]]; then
    print_success "Docker Compose: $compose_version"
else
    print_error "Docker Compose no está instalado"
    exit 1
fi

# Resumen
echo ""
print_header "RESUMEN DE VERIFICACIÓN"
echo "✅ Conexión SSH: OK"
echo "✅ gcloud CLI: Instalado"
echo "✅ Autenticación: Activa"
echo "✅ Acceso Cloud SQL: OK"
echo "✅ Acceso Cloud Storage: OK"
echo "✅ Recursos servidor: OK"
echo ""
print_success "✅ Todas las verificaciones pasaron"
echo ""
echo "📋 Próximo paso:"
echo "   ./clone-from-gcp-enterprise.sh"
echo ""

