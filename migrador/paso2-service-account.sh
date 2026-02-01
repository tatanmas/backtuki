#!/bin/bash

# 🔐 PASO 2: CONFIGURAR CREDENCIALES CON SERVICE ACCOUNT
# Usa Service Account Key en vez de login interactivo (más robusto para servidores)
# 
# IMPORTANTE: Este método NO requiere navegador en el servidor.
# El navegador solo se usa en tu Mac para crear el Service Account.
# La clave JSON se transfiere al servidor donde gcloud la usa sin interfaz gráfica.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SSH_HOST="tukitickets.duckdns.org"
SSH_PORT="2222"
SSH_USER="tatan"
SSH_PASS="rollolupita"
PROJECT_ID="tukiprod"
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

echo "🔐 PASO 2: CONFIGURAR CREDENCIALES CON SERVICE ACCOUNT"
echo "======================================================"
echo ""
print_info "Este método NO requiere navegador en el servidor"
print_info "El navegador solo se usa en tu Mac para crear el Service Account"
print_info "Una vez configurado, el servidor accede a GCP automáticamente"
echo ""

# Verificar que gcloud está disponible localmente
if ! command -v gcloud &> /dev/null; then
    print_error "gcloud CLI no está instalado en tu Mac"
    print_info "Instala desde: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

print_success "gcloud CLI encontrado en tu Mac"

# Paso 1: Verificar que estás autenticado en tu Mac
print_step "Paso 1: Verificando autenticación en tu Mac..."

AUTH_ACCOUNTS=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null || echo "")

if [[ -z "$AUTH_ACCOUNTS" ]]; then
    print_error "No estás autenticado en gcloud en tu Mac"
    echo ""
    print_info "Necesitas hacer login primero en tu Mac (usa tu navegador):"
    echo ""
    echo "  gcloud auth login"
    echo ""
    print_info "Esto abrirá tu navegador. Inicia sesión con tecnologia@tuki.cl"
    exit 1
fi

print_success "Autenticado como: $AUTH_ACCOUNTS"

# Intentar configurar proyecto directamente (fallará si token expiró)
print_info "Configurando proyecto..."
if ! gcloud config set project "$PROJECT_ID" 2>/dev/null; then
    print_error "Error al configurar proyecto"
    print_warning "Posibles causas:"
    print_warning "  1. Token expirado - ejecuta: gcloud auth login"
    print_warning "  2. Sin permisos en el proyecto - verifica IAM"
    exit 1
fi

print_success "Proyecto configurado: $PROJECT_ID"

# Verificar permisos del usuario para crear Service Accounts
print_step "Verificando permisos del usuario..."

CURRENT_ACCOUNT=$(gcloud config get-value account 2>/dev/null || echo "")
if [[ -z "$CURRENT_ACCOUNT" ]]; then
    print_error "No se puede obtener cuenta actual"
    exit 1
fi

# Verificar si el usuario tiene permisos necesarios
print_info "Verificando permisos para crear Service Accounts..."
if ! gcloud projects get-iam-policy "$PROJECT_ID" --flatten="bindings[].members" --filter="bindings.members:user:${CURRENT_ACCOUNT}" --format="value(bindings.role)" 2>/dev/null | grep -qE "(roles/owner|roles/iam.serviceAccountAdmin|roles/iam.serviceAccountKeyAdmin)"; then
    print_warning "El usuario puede que no tenga permisos para crear Service Accounts"
    print_info "Roles necesarios: roles/iam.serviceAccountAdmin o roles/owner"
    print_info "Intentando crear de todas formas..."
fi

# Paso 2: Crear o usar Service Account existente
print_step "Paso 2: Creando o usando Service Account..."

SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

print_info "Verificando si Service Account ya existe..."
if gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" &>/dev/null 2>&1; then
    print_warning "Service Account ya existe: $SERVICE_ACCOUNT_EMAIL"
    read -p "¿Deseas usar el existente, recrearlo, o solo actualizar permisos? (use/recreate/update): " choice
    choice=${choice:-use}
    
    if [[ "$choice" == "recreate" ]]; then
        print_info "Eliminando Service Account existente..."
        if gcloud iam service-accounts delete "$SERVICE_ACCOUNT_EMAIL" --quiet 2>/dev/null; then
            print_success "Service Account eliminado"
        else
            print_error "Error al eliminar Service Account. Puede que tenga dependencias."
            exit 1
        fi
        print_info "Creando nuevo Service Account..."
        if gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
            --display-name="Tuki Home Server Migrator" \
            --description="Service Account para migración desde GCP a servidor local" \
            --project="$PROJECT_ID" 2>/dev/null; then
            print_success "Service Account creado"
        else
            print_error "Error al crear Service Account. Verifica permisos."
            exit 1
        fi
    elif [[ "$choice" == "update" ]]; then
        print_info "Manteniendo Service Account existente, solo actualizaremos permisos"
    else
        print_success "Usando Service Account existente"
    fi
else
    print_info "Creando Service Account..."
    if gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
        --display-name="Tuki Home Server Migrator" \
        --description="Service Account para migración desde GCP a servidor local" \
        --project="$PROJECT_ID" 2>/dev/null; then
        print_success "Service Account creado: $SERVICE_ACCOUNT_EMAIL"
    else
        print_error "Error al crear Service Account"
        print_warning "Posibles causas:"
        print_warning "  1. Sin permisos roles/iam.serviceAccountAdmin"
        print_warning "  2. Nombre duplicado o inválido"
        print_warning "  3. Límite de Service Accounts alcanzado"
        exit 1
    fi
fi

# Paso 3: Asignar roles necesarios
print_step "Paso 3: Asignando permisos al Service Account..."

# Roles necesarios (principio de menor privilegio)
ROLES=(
    "roles/cloudsql.client"           # Acceso a Cloud SQL
    "roles/storage.objectViewer"      # Leer desde Cloud Storage
    "roles/storage.objectCreator"     # Escribir backups en Cloud Storage
)

print_info "Asignando roles con principio de menor privilegio..."
for role in "${ROLES[@]}"; do
    print_info "Asignando rol: $role"
    if gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
        --role="$role" \
        --condition=None \
        --quiet 2>/dev/null; then
        print_success "Rol $role asignado"
    else
        # Verificar si ya está asignado
        if gcloud projects get-iam-policy "$PROJECT_ID" \
            --flatten="bindings[].members" \
            --filter="bindings.members:serviceAccount:${SERVICE_ACCOUNT_EMAIL} AND bindings.role:${role}" \
            --format="value(bindings.role)" 2>/dev/null | grep -q "$role"; then
            print_info "Rol $role ya está asignado"
        else
            print_warning "No se pudo asignar rol $role. Verifica permisos."
        fi
    fi
done

print_success "Permisos verificados/asignados"

# Paso 4: Intentar crear key JSON (puede estar bloqueado por política de organización)
print_step "Paso 4: Intentando crear key JSON..."

KEY_FILE="${SCRIPT_DIR}/gcp-key-${SERVICE_ACCOUNT_NAME}.json"

# Limpiar key anterior si existe
if [[ -f "$KEY_FILE" ]]; then
    print_warning "Key JSON existente encontrada. Se creará una nueva."
    rm -f "$KEY_FILE"
fi

print_info "Intentando descargar key JSON a: $KEY_FILE"
# Intentar crear key con timeout implícito (si se cuelga, asumimos que está bloqueado)
# Usamos un proceso en background con kill después de 5 segundos
(gcloud iam service-accounts keys create "$KEY_FILE" \
    --iam-account="$SERVICE_ACCOUNT_EMAIL" \
    --project="$PROJECT_ID" > /tmp/key-create.log 2>&1) &
KEY_PID=$!
sleep 5
if kill -0 $KEY_PID 2>/dev/null; then
    # El proceso sigue corriendo, probablemente bloqueado
    kill $KEY_PID 2>/dev/null
    wait $KEY_PID 2>/dev/null
    KEY_CREATION_OUTPUT=$(cat /tmp/key-create.log 2>/dev/null || echo "TIMEOUT - Key creation blocked by policy")
    KEY_CREATION_EXIT=1
    rm -f /tmp/key-create.log
else
    # El proceso terminó
    wait $KEY_PID
    KEY_CREATION_EXIT=$?
    KEY_CREATION_OUTPUT=$(cat /tmp/key-create.log 2>/dev/null || echo "")
    rm -f /tmp/key-create.log
fi

if [[ $KEY_CREATION_EXIT -eq 0 ]] && [[ -f "$KEY_FILE" ]] && [[ -s "$KEY_FILE" ]]; then
    # Asegurar permisos seguros
    chmod 600 "$KEY_FILE"
    print_success "Key JSON descargada y protegida (chmod 600)"
    print_warning "⚠️  IMPORTANTE: Este archivo contiene credenciales sensibles"
    print_warning "   - Manténlo seguro y NO lo subas a Git"
    print_warning "   - NO lo compartas"
    print_warning "   - Rota las claves periódicamente (cada 90 días recomendado)"
    USE_KEY_FILE=true
else
    # Verificar si es por política de organización
    if echo "$KEY_CREATION_OUTPUT" | grep -qi "disableServiceAccountKeyCreation\|Key creation is not allowed"; then
        print_warning "⚠️  La creación de keys está bloqueada por política de organización"
        print_info "Usaremos impersonación de Service Account en su lugar (más seguro)"
        USE_KEY_FILE=false
    else
        print_warning "⚠️  No se pudo crear key JSON"
        if echo "$KEY_CREATION_OUTPUT" | grep -qi "ERROR"; then
            print_info "Error detectado: $(echo "$KEY_CREATION_OUTPUT" | grep -i "ERROR" | head -1)"
        fi
        print_info "Usaremos impersonación de Service Account en su lugar"
        USE_KEY_FILE=false
    fi
fi

# Paso 5: Subir key al servidor (solo si se creó exitosamente)
if [[ "$USE_KEY_FILE" == "true" ]]; then
    print_step "Paso 5: Subiendo key JSON al servidor..."
    
    print_info "Subiendo archivo al servidor..."
    
    expect << EOF
set timeout 30
spawn scp -P ${SSH_PORT} "$KEY_FILE" ${SSH_USER}@${SSH_HOST}:~/gcp-key.json
expect {
    "password:" {
        send "${SSH_PASS}\r"
    }
    timeout {
        puts "Timeout"
        exit 1
    }
}
expect eof
EOF
    
    if [[ $? -eq 0 ]]; then
        print_success "Key JSON subida al servidor"
    else
        print_error "Error al subir key JSON"
        exit 1
    fi
else
    print_step "Paso 5: Saltando transferencia de key (usaremos impersonación)"
fi

# Paso 6: Configurar gcloud en el servidor
print_step "Paso 6: Configurando gcloud en el servidor..."

# Verificar que gcloud está instalado en el servidor
print_info "Verificando que gcloud está instalado en el servidor..."
expect << 'VERIFY_GCLOUD' > /tmp/gcloud-check.log 2>&1
set timeout 30
spawn ssh -o StrictHostKeyChecking=no -p 2222 tatan@tukitickets.duckdns.org
expect {
    "password:" {
        send "rollolupita\r"
    }
    timeout {
        puts "Timeout"
        exit 1
    }
}
expect "$ "
send "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && which gcloud && gcloud --version | head -1\r"
expect "$ "
send "exit\r"
expect eof
VERIFY_GCLOUD

if grep -q "command not found" /tmp/gcloud-check.log; then
    print_error "gcloud no está instalado en el servidor"
    print_info "Ejecuta primero: ./paso1-instalar-gcloud.sh"
    rm -f /tmp/gcloud-check.log
    exit 1
fi
rm -f /tmp/gcloud-check.log
print_success "gcloud está instalado en el servidor"

# Configurar credenciales según el método disponible
if [[ "$USE_KEY_FILE" == "true" ]]; then
    print_info "Configurando credenciales con Service Account Key..."
    expect << EOF
set timeout 60
spawn ssh -o StrictHostKeyChecking=no -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST}
expect {
    "password:" {
        send "${SSH_PASS}\r"
    }
    timeout {
        puts "Timeout"
        exit 1
    }
}
expect "$ "
send "export PATH=\\\$PATH:\\\$HOME/google-cloud-sdk/bin\r"
expect "$ "
send "chmod 600 /home/tatan/gcp-key.json\r"
expect "$ "
send "gcloud auth activate-service-account --key-file=/home/tatan/gcp-key.json\r"
expect "$ "
send "gcloud config set project ${PROJECT_ID}\r"
expect "$ "
send "gcloud config list\r"
expect "$ "
send "gcloud auth list\r"
expect "$ "
send "exit\r"
expect eof
EOF
else
    print_info "Configurando credenciales con impersonación de Service Account..."
    print_warning "Necesitarás autenticarte en el servidor primero"
    print_info "El script iniciará un proceso de login interactivo"
    echo ""
    read -p "Presiona Enter para continuar con el login en el servidor..."
    
    expect << EOF
set timeout 300
spawn ssh -o StrictHostKeyChecking=no -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST}
expect {
    "password:" {
        send "${SSH_PASS}\r"
    }
    timeout {
        puts "Timeout"
        exit 1
    }
}
expect "$ "
send "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin\r"
expect "$ "
send "gcloud auth login --no-launch-browser\r"
expect {
    "Enter verification code:" {
        puts "\n"
        puts "═══════════════════════════════════════════════════════════"
        puts "📋 COPIA LA URL QUE APARECE ARRIBA"
        puts "🌐 Ábrela en tu navegador"
        puts "🔑 Inicia sesión con: tecnologia@tuki.cl"
        puts "📝 Copia el código de verificación"
        puts "═══════════════════════════════════════════════════════════"
        puts "\n"
    }
    timeout {
        puts "Timeout esperando código"
        exit 1
    }
}
expect "Enter verification code:"
puts "\nPega el código aquí y presiona Enter: "
expect_user -re "(.*)\n"
set code \$expect_out(1,string)
send "\$code\r"
expect "$ "
send "gcloud config set project ${PROJECT_ID}\r"
expect "$ "
send "gcloud config set auth/impersonate_service_account ${SERVICE_ACCOUNT_EMAIL}\r"
expect "$ "
send "gcloud config list\r"
expect "$ "
send "gcloud auth list\r"
expect "$ "
send "exit\r"
expect eof
EOF
fi

if [[ $? -eq 0 ]]; then
    print_success "gcloud configurado en el servidor"
else
    print_error "Error al configurar gcloud en el servidor"
    exit 1
fi

# Paso 7: Verificar acceso
print_step "Paso 7: Verificando acceso desde el servidor..."

print_info "Verificando acceso a Cloud SQL..."
SQL_CHECK=$(expect << 'SQL_VERIFY'
set timeout 60
log_user 0
spawn ssh -o StrictHostKeyChecking=no -p 2222 tatan@tukitickets.duckdns.org
expect {
    "password:" {
        send "rollolupita\r"
    }
    timeout {
        puts "TIMEOUT"
        exit 1
    }
}
expect "$ "
send "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gcloud sql instances describe tuki-db-prod --project=tukiprod --format='value(name)' 2>&1\r"
expect {
    "tuki-db-prod" {
        puts "OK"
    }
    -re "ERROR|error|denied" {
        puts "ERROR"
    }
    timeout {
        puts "TIMEOUT"
    }
    "$ " {
        send "exit\r"
    }
}
expect eof
SQL_VERIFY
)

if echo "$SQL_CHECK" | grep -q "OK"; then
    print_success "Acceso a Cloud SQL verificado"
else
    print_error "Error al acceder a Cloud SQL"
    print_warning "Verifica que el Service Account tenga el rol roles/cloudsql.client"
fi

print_info "Verificando acceso a Cloud Storage..."
STORAGE_CHECK=$(expect << 'STORAGE_VERIFY'
set timeout 60
log_user 0
spawn ssh -o StrictHostKeyChecking=no -p 2222 tatan@tukitickets.duckdns.org
expect {
    "password:" {
        send "rollolupita\r"
    }
    timeout {
        puts "TIMEOUT"
        exit 1
    }
}
expect "$ "
send "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gsutil ls gs://tuki-media-prod-1759240560/ 2>&1 | head -1\r"
expect {
    "gs://" {
        puts "OK"
    }
    -re "ERROR|error|denied|AccessDenied" {
        puts "ERROR"
    }
    timeout {
        puts "TIMEOUT"
    }
    "$ " {
        send "exit\r"
    }
}
expect eof
STORAGE_VERIFY
)

if echo "$STORAGE_CHECK" | grep -q "OK"; then
    print_success "Acceso a Cloud Storage verificado"
else
    print_error "Error al acceder a Cloud Storage"
    print_warning "Verifica que el Service Account tenga el rol roles/storage.objectViewer"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
print_success "✅ CREDENCIALES CONFIGURADAS CON SERVICE ACCOUNT"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📋 RESUMEN:"
echo "   Service Account: ${SERVICE_ACCOUNT_EMAIL}"
echo "   Key JSON local: ${KEY_FILE}"
echo "   Key JSON servidor: ~/gcp-key.json (chmod 600)"
echo "   Proyecto: ${PROJECT_ID}"
echo ""
print_warning "⚠️  IMPORTANTE - Seguridad:"
print_warning "   - Mantén el archivo ${KEY_FILE} seguro"
print_warning "   - NO lo subas a Git (verifica .gitignore)"
print_warning "   - Rota las claves periódicamente (cada 90 días)"
print_warning "   - Revoca claves antiguas si las reemplazas"
echo ""
echo "📋 Próximo paso:"
echo "   ./verificar-autenticacion.sh  (verificación detallada)"
echo "   ./paso3-verificar-acceso.sh   (verificación completa)"
echo ""

