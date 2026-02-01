#!/bin/bash

# ✅ VERIFICAR AUTENTICACIÓN GCP EN SERVIDOR
# Script para verificar que la autenticación con Service Account funciona correctamente

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SSH_HOST="tukitickets.duckdns.org"
SSH_PORT="2222"
SSH_USER="tatan"
SSH_PASS="rollolupita"
PROJECT_ID="tukiprod"
CLOUD_SQL_INSTANCE="tuki-db-prod"
GCS_BUCKET="tuki-media-prod-1759240560"
SERVICE_ACCOUNT_NAME="tuki-homeserver-migrator"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_step() { echo -e "${BLUE}🔧 $1${NC}"; }
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }
print_info() { echo -e "${CYAN}ℹ️  $1${NC}"; }

echo "✅ VERIFICAR AUTENTICACIÓN GCP EN SERVIDOR"
echo "=========================================="
echo ""

VERIFICATION_FAILED=0

# Función para ejecutar comando SSH y capturar output
ssh_exec_capture() {
    local cmd="$1"
    local timeout="${2:-30}"
    
    expect << EOF 2>/dev/null | grep -v "^spawn\|^expect\|^send\|^Connection\|^Last login" | grep -v "^Linux\|^The programs\|^Debian"
set timeout ${timeout}
log_user 0
spawn ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST}
expect {
    "password:" {
        send "${SSH_PASS}\r"
        exp_continue
    }
    timeout {
        puts "TIMEOUT"
        exit 1
    }
}
expect "$ "
send "${cmd}\r"
expect {
    "$ " {
        send "exit\r"
    }
    timeout {
        send "exit\r"
    }
}
expect eof
EOF
}

# 1. Verificar conexión SSH
print_step "1. Verificando conexión SSH..."
if ssh_exec_capture "echo 'SSH_OK'" 10 | grep -q "SSH_OK"; then
    print_success "Conexión SSH establecida"
else
    print_error "No se puede conectar via SSH"
    exit 1
fi

# 2. Verificar gcloud instalado
print_step "2. Verificando gcloud CLI..."
GCLOUD_VERSION=$(ssh_exec_capture "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gcloud --version 2>/dev/null | head -1" 30)
if echo "$GCLOUD_VERSION" | grep -q "Google Cloud SDK"; then
    print_success "gcloud CLI instalado: $(echo "$GCLOUD_VERSION" | head -1)"
else
    print_error "gcloud CLI no está instalado"
    print_info "Ejecuta primero: ./paso1-instalar-gcloud.sh"
    exit 1
fi

# 3. Verificar autenticación
print_step "3. Verificando autenticación gcloud..."
AUTH_LIST=$(ssh_exec_capture "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gcloud auth list 2>/dev/null" 30)
if echo "$AUTH_LIST" | grep -q "ACTIVE"; then
    print_success "Autenticación activa"
    ACTIVE_ACCOUNT=$(echo "$AUTH_LIST" | grep "ACTIVE" | awk '{print $2}')
    print_info "Cuenta activa: $ACTIVE_ACCOUNT"
    
    # Verificar que es un Service Account
    if echo "$ACTIVE_ACCOUNT" | grep -q "@.*\.iam\.gserviceaccount\.com"; then
        print_success "Usando Service Account (correcto)"
    else
        print_warning "No está usando Service Account"
    fi
else
    print_error "No hay cuentas autenticadas"
    VERIFICATION_FAILED=1
fi

# 4. Verificar proyecto configurado
print_step "4. Verificando proyecto configurado..."
CONFIG_PROJECT=$(ssh_exec_capture "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gcloud config get-value project 2>/dev/null" 30)
if [[ "$CONFIG_PROJECT" == "$PROJECT_ID" ]]; then
    print_success "Proyecto configurado: $PROJECT_ID"
else
    print_error "Proyecto incorrecto: $CONFIG_PROJECT (esperado: $PROJECT_ID)"
    VERIFICATION_FAILED=1
fi

# 5. Verificar archivo JSON existe y tiene permisos correctos
print_step "5. Verificando archivo JSON..."
JSON_CHECK=$(ssh_exec_capture "test -f ~/gcp-key.json && ls -l ~/gcp-key.json | awk '{print \$1}'" 10)
if echo "$JSON_CHECK" | grep -q "\-rw\-\-\-\-\-\-\-"; then
    print_success "Archivo JSON existe con permisos correctos (600)"
elif echo "$JSON_CHECK" | grep -q "^-rw"; then
    PERMS=$(echo "$JSON_CHECK" | awk '{print $1}')
    print_warning "Archivo JSON existe pero permisos son: $PERMS (debería ser 600)"
    print_info "Ejecuta en el servidor: chmod 600 ~/gcp-key.json"
else
    print_error "Archivo JSON no encontrado o sin permisos"
    VERIFICATION_FAILED=1
fi

# 6. Verificar acceso a Cloud SQL
print_step "6. Verificando acceso a Cloud SQL..."
SQL_CHECK=$(ssh_exec_capture "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gcloud sql instances describe ${CLOUD_SQL_INSTANCE} --project=${PROJECT_ID} --format='value(name)' 2>&1" 60)
if echo "$SQL_CHECK" | grep -q "${CLOUD_SQL_INSTANCE}"; then
    print_success "Acceso a Cloud SQL verificado"
    print_info "Instancia: ${CLOUD_SQL_INSTANCE}"
elif echo "$SQL_CHECK" | grep -qi "permission\|denied\|403"; then
    print_error "Sin permisos para acceder a Cloud SQL"
    print_info "Verifica que el Service Account tenga el rol: roles/cloudsql.client"
    VERIFICATION_FAILED=1
elif echo "$SQL_CHECK" | grep -qi "not found\|404"; then
    print_error "Instancia Cloud SQL no encontrada"
    VERIFICATION_FAILED=1
else
    print_warning "Error al verificar Cloud SQL: $(echo "$SQL_CHECK" | head -2)"
    VERIFICATION_FAILED=1
fi

# 7. Verificar acceso a Cloud Storage
print_step "7. Verificando acceso a Cloud Storage..."
STORAGE_CHECK=$(ssh_exec_capture "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gsutil ls gs://${GCS_BUCKET}/ 2>&1 | head -3" 60)
if echo "$STORAGE_CHECK" | grep -q "gs://"; then
    print_success "Acceso a Cloud Storage verificado"
    print_info "Bucket: gs://${GCS_BUCKET}/"
    OBJECT_COUNT=$(echo "$STORAGE_CHECK" | wc -l | tr -d ' ')
    print_info "Objetos listados: $OBJECT_COUNT"
elif echo "$STORAGE_CHECK" | grep -qi "access.*denied\|403"; then
    print_error "Sin permisos para acceder a Cloud Storage"
    print_info "Verifica que el Service Account tenga los roles:"
    print_info "  - roles/storage.objectViewer (leer)"
    print_info "  - roles/storage.objectCreator (escribir, si es necesario)"
    VERIFICATION_FAILED=1
elif echo "$STORAGE_CHECK" | grep -qi "not found\|404"; then
    print_error "Bucket de Cloud Storage no encontrado"
    VERIFICATION_FAILED=1
else
    print_warning "Error al verificar Cloud Storage: $(echo "$STORAGE_CHECK" | head -2)"
    VERIFICATION_FAILED=1
fi

# 8. Verificar Service Account tiene roles correctos
print_step "8. Verificando roles del Service Account..."
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
print_info "Service Account: $SERVICE_ACCOUNT_EMAIL"

# Verificar desde Mac (si está autenticado)
if command -v gcloud &> /dev/null; then
    if gcloud projects get-iam-policy "$PROJECT_ID" \
        --flatten="bindings[].members" \
        --filter="bindings.members:serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
        --format="value(bindings.role)" 2>/dev/null | grep -q "cloudsql.client"; then
        print_success "Rol roles/cloudsql.client asignado"
    else
        print_warning "Rol roles/cloudsql.client no encontrado"
    fi
    
    if gcloud projects get-iam-policy "$PROJECT_ID" \
        --flatten="bindings[].members" \
        --filter="bindings.members:serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
        --format="value(bindings.role)" 2>/dev/null | grep -q "storage.objectViewer"; then
        print_success "Rol roles/storage.objectViewer asignado"
    else
        print_warning "Rol roles/storage.objectViewer no encontrado"
    fi
else
    print_info "gcloud no está en PATH local, saltando verificación de roles desde Mac"
fi

# Resumen final
echo ""
echo "═══════════════════════════════════════════════════════════"
if [[ $VERIFICATION_FAILED -eq 0 ]]; then
    print_success "✅ TODAS LAS VERIFICACIONES PASARON"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    print_success "El servidor está correctamente configurado para acceder a GCP"
    echo ""
    echo "📋 Puedes continuar con:"
    echo "   ./paso3-verificar-acceso.sh  (verificación completa del sistema)"
    echo "   ./clone-from-gcp-enterprise.sh  (clonar desde GCP)"
    exit 0
else
    print_error "❌ ALGUNAS VERIFICACIONES FALLARON"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    print_warning "Revisa los errores arriba y consulta:"
    echo "   ./TROUBLESHOOTING_AUTH.md  (guía de solución de problemas)"
    echo ""
    print_info "O ejecuta nuevamente:"
    echo "   ./paso2-service-account.sh  (reconfigurar credenciales)"
    exit 1
fi

