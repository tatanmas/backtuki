#!/bin/bash

# 🔐 PASO 2: CONFIGURAR CREDENCIALES GCP
# Este script configura la autenticación con Google Cloud

set -e

SSH_HOST="tukitickets.duckdns.org"
SSH_PORT="2222"
SSH_USER="tatan"
SSH_PASS="rollolupita"
PROJECT_ID="tukiprod"

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

echo "🔐 PASO 2: CONFIGURAR CREDENCIALES GCP"
echo "======================================="
echo ""

print_step "Iniciando autenticación con Google Cloud..."
echo ""
print_warning "Se abrirá un proceso de login interactivo."
print_warning "Necesitarás copiar una URL y abrirla en tu navegador."
echo ""

# Ejecutar login interactivo
expect << EOF
set timeout 300
spawn ssh -o StrictHostKeyChecking=no -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST}
expect "password:"
send "${SSH_PASS}\r"
expect "$ "
send "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin\r"
expect "$ "
send "gcloud auth login --no-launch-browser\r"
expect {
    "Enter verification code:" {
        print_success "Por favor, copia la URL que aparece arriba y ábrela en tu navegador"
        print_success "Luego copia el código de verificación y pégalo aquí"
        interact
    }
    "You are now logged in" {
        print_success "Login exitoso"
    }
    timeout {
        print_error "Timeout esperando autenticación"
        exit 1
    }
}
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

print_success "✅ Credenciales configuradas"
echo ""
echo "📋 Próximo paso:"
echo "   Ejecutar: ./paso3-verificar-acceso.sh"
echo ""

