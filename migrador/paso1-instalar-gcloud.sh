#!/bin/bash

# 🔧 PASO 1: INSTALAR GCLOUD CLI EN EL SERVIDOR
# Este script instala gcloud CLI en tu servidor local

set -e

SSH_HOST="tukitickets.duckdns.org"
SSH_PORT="2222"
SSH_USER="tatan"
SSH_PASS="rollolupita"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

print_step() { echo -e "${BLUE}🔧 $1${NC}"; }
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }

echo "🔧 PASO 1: INSTALAR GCLOUD CLI"
echo "==============================="
echo ""

# Función para ejecutar comandos via SSH y mostrar output
ssh_exec_visible() {
    expect << EOF
set timeout 300
spawn ssh -o StrictHostKeyChecking=no -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST}
expect "password:"
send "${SSH_PASS}\r"
expect "$ "
send "$1\r"
expect "$ "
send "exit\r"
expect eof
EOF
}

print_step "Instalando gcloud CLI en el servidor..."
print_warning "⏱️  Esto puede tomar 2-3 minutos..."

# Instalar gcloud CLI usando el instalador oficial
ssh_exec_visible "curl https://sdk.cloud.google.com | bash"

print_success "gcloud CLI descargado"

# Agregar al PATH y verificar
print_step "Configurando PATH..."

ssh_exec_visible "echo 'export PATH=\$PATH:\$HOME/google-cloud-sdk/bin' >> ~/.bashrc && source ~/.bashrc && export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gcloud --version"

print_success "✅ gcloud CLI instalado correctamente"
echo ""
echo "📋 Próximo paso:"
echo "   Ejecutar: ./paso2-configurar-credenciales.sh"
echo ""

