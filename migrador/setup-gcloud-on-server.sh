#!/bin/bash

# 🔧 SETUP GCLOUD CLI EN SERVIDOR LOCAL
# Este script instala gcloud CLI y configura credenciales

set -e

SSH_HOST="tukitickets.duckdns.org"
SSH_PORT="2222"
SSH_USER="tatan"
SSH_PASS="rollolupita"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_step() { echo -e "${BLUE}🔧 $1${NC}"; }
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }

echo "🔧 CONFIGURANDO GCLOUD CLI EN SERVIDOR"
echo "======================================"
echo ""

# Función para ejecutar comandos via SSH
ssh_exec() {
    expect << EOF
set timeout 60
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

# PASO 1: Verificar si gcloud ya está instalado
print_step "Paso 1: Verificando si gcloud CLI está instalado..."

ssh_exec "which gcloud && gcloud --version || echo 'NO_INSTALLED'"

read -p "¿Está gcloud instalado? (yes/no): " gcloud_installed

if [ "$gcloud_installed" != "yes" ]; then
    print_step "Instalando gcloud CLI..."
    
    # Instalar gcloud CLI
    ssh_exec "curl https://sdk.cloud.google.com | bash && exec -l \$SHELL"
    
    # Agregar al PATH
    ssh_exec "echo 'export PATH=\$PATH:\$HOME/google-cloud-sdk/bin' >> ~/.bashrc && source ~/.bashrc"
    
    print_success "gcloud CLI instalado"
else
    print_success "gcloud CLI ya está instalado"
fi

echo ""
print_step "Paso 2: Configurando credenciales..."
echo ""
print_warning "OPCIÓN A: Login interactivo (requiere navegador)"
print_warning "OPCIÓN B: Service Account Key (más seguro para servidor)"
echo ""
read -p "¿Qué método prefieres? (A/B): " auth_method

if [ "$auth_method" = "A" ]; then
    # Login interactivo
    print_step "Iniciando login interactivo..."
    print_warning "Se abrirá una URL en tu navegador. Cópiala y ábrela."
    
    ssh_exec "gcloud auth login --no-launch-browser"
    
    print_success "Login completado"
    
elif [ "$auth_method" = "B" ]; then
    # Service Account
    print_step "Configurando Service Account..."
    echo ""
    echo "Necesitas crear un Service Account en GCP:"
    echo "1. Ve a: https://console.cloud.google.com/iam-admin/serviceaccounts?project=tukiprod"
    echo "2. Crea un nuevo Service Account llamado 'tuki-homeserver'"
    echo "3. Asigna roles: Cloud SQL Client, Storage Object Viewer"
    echo "4. Crea una key JSON y descárgala"
    echo ""
    read -p "Presiona Enter cuando tengas el archivo JSON descargado..."
    
    read -p "Ruta completa del archivo JSON en tu Mac: " json_path
    
    if [ -f "$json_path" ]; then
        print_step "Subiendo key JSON al servidor..."
        
        # Subir archivo
        expect << EOF
set timeout 30
spawn scp -P ${SSH_PORT} "$json_path" ${SSH_USER}@${SSH_HOST}:~/gcp-key.json
expect "password:"
send "${SSH_PASS}\r"
expect eof
EOF
        
        # Configurar credenciales
        ssh_exec "gcloud auth activate-service-account --key-file=~/gcp-key.json"
        ssh_exec "gcloud config set project tukiprod"
        
        print_success "Service Account configurado"
    else
        print_error "Archivo no encontrado: $json_path"
        exit 1
    fi
fi

# Verificar configuración
print_step "Verificando configuración..."
ssh_exec "gcloud config list && gcloud auth list"

print_success "✅ gcloud CLI configurado correctamente"
echo ""
echo "📋 Próximos pasos:"
echo "1. Verificar que puedes acceder a Cloud SQL"
echo "2. Verificar que puedes acceder a Cloud Storage"
echo "3. Ejecutar script de clonación"

