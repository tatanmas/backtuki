#!/bin/bash

# 🔐 PASO 2: LOGIN GCLOUD - ENTERPRISE
# Script robusto con logging, verificaciones y manejo de errores

set -euo pipefail

# Cargar librería común
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

# Inicializar logging
init_logging

print_header "PASO 2: CONFIGURAR CREDENCIALES GCP - ENTERPRISE"

# Verificaciones previas
print_step "Ejecutando verificaciones previas..."

if ! verify_ssh_connection; then
    print_error "No se puede conectar al servidor"
    exit 1
fi

if ! verify_gcloud_installed; then
    print_error "gcloud CLI no está instalado. Ejecuta primero: ./paso1-instalar-gcloud.sh"
    exit 1
fi

# Verificar si ya está autenticado
if verify_gcloud_auth; then
    print_warning "Ya hay una sesión activa en gcloud"
    read -p "¿Deseas autenticarte de nuevo? (yes/no): " reauth
    if [[ "$reauth" != "yes" ]]; then
        print_success "Usando autenticación existente"
        exit 0
    fi
fi

# Crear punto de backup
create_backup_point "pre-login"

# Ejecutar login
print_step "Iniciando proceso de autenticación..."
print_info "Se abrirá un proceso interactivo"
print_info "Necesitarás:"
print_info "  1. Copiar la URL que aparecerá"
print_info "  2. Abrirla en tu navegador"
print_info "  3. Iniciar sesión con: tecnologia@tuki.cl"
print_info "  4. Copiar el código de verificación"
print_info "  5. Pegarlo aquí"
echo ""
read -p "Presiona Enter para continuar..."

# Login interactivo
expect << 'EXPECT_SCRIPT'
set timeout 300
spawn ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p 2222 tatan@tukitickets.duckdns.org
expect {
    "password:" {
        send "rollolupita\r"
    }
    timeout {
        puts "\n❌ Timeout conectando al servidor\n"
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
        puts "🔐 INSTRUCCIONES DE AUTENTICACIÓN"
        puts "═══════════════════════════════════════════════════════════"
        puts ""
        puts "1. 📋 Copia la URL que aparece arriba"
        puts "2. 🌐 Ábrela en tu navegador"
        puts "3. 🔑 Inicia sesión con:"
        puts "   Email: tecnologia@tuki.cl"
        puts "   Password: >2gfbinrlFQ6"
        puts "4. 📝 Copia el código de verificación"
        puts "5. 📥 Pégalo aquí abajo y presiona Enter"
        puts ""
        puts "═══════════════════════════════════════════════════════════"
        puts ""
        interact
    }
    "You are now logged in" {
        puts "\n✅ Login exitoso\n"
    }
    timeout {
        puts "\n❌ Timeout esperando autenticación\n"
        exit 1
    }
}
expect "$ "
send "gcloud config set project tukiprod\r"
expect "$ "
send "gcloud config list\r"
expect "$ "
send "gcloud auth list\r"
expect "$ "
send "exit\r"
expect eof
EXPECT_SCRIPT

login_exit_code=$?

if [[ $login_exit_code -ne 0 ]]; then
    print_error "Error durante el proceso de login"
    exit 1
fi

# Verificar autenticación
print_step "Verificando autenticación..."

if verify_gcloud_auth; then
    print_success "✅ Autenticación configurada correctamente"
    
    # Verificar proyecto
    local project=$(ssh_exec_with_output "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gcloud config get-value project 2>/dev/null" 30)
    if [[ "$project" == "tukiprod" ]]; then
        print_success "Proyecto configurado: $project"
    else
        print_warning "Proyecto no configurado correctamente. Configurando..."
        ssh_exec "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin && gcloud config set project tukiprod" 30
    fi
    
    # Crear punto de backup post-login
    create_backup_point "post-login"
    
    echo ""
    print_header "RESUMEN"
    echo "✅ gcloud CLI instalado"
    echo "✅ Autenticación configurada"
    echo "✅ Proyecto: tukiprod"
    echo ""
    echo "📋 Próximo paso:"
    echo "   ./paso3-verificar-acceso.sh"
    echo ""
    print_success "Paso 2 completado exitosamente"
else
    print_error "La autenticación no se completó correctamente"
    exit 1
fi

