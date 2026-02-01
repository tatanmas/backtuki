#!/bin/bash

# 🔐 PASO 2: LOGIN GCLOUD - SIMPLE E INTERACTIVO
# Script simple que te guía paso a paso para hacer login

SSH_HOST="tukitickets.duckdns.org"
SSH_PORT="2222"
SSH_USER="tatan"
SSH_PASS="rollolupita"

echo "🔐 PASO 2: CONFIGURAR CREDENCIALES GCP"
echo "======================================="
echo ""
echo "Este script te ayudará a hacer login en gcloud."
echo "Necesitarás copiar una URL y abrirla en tu navegador."
echo ""
read -p "Presiona Enter para continuar..."

# Conectar y ejecutar login interactivo
expect << 'EXPECT_SCRIPT'
set timeout 300
spawn ssh -o StrictHostKeyChecking=no -p 2222 tatan@tukitickets.duckdns.org
expect {
    "password:" {
        send "rollolupita\r"
    }
    timeout {
        puts "\n❌ Timeout conectando\n"
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
        puts "ARRIBA verás una URL que empieza con:"
        puts "https://accounts.google.com/o/oauth2/auth?..."
        puts ""
        puts "📋 PASOS:"
        puts "   1. Copia TODA esa URL completa"
        puts "   2. Ábrela en tu navegador"
        puts "   3. Inicia sesión con:"
        puts "      Email: tecnologia@tuki.cl"
        puts "      Password: >2gfbinrlFQ6"
        puts "   4. Autoriza el acceso"
        puts "   5. Copia el código de verificación que aparece"
        puts "   6. Pégalo aquí abajo y presiona Enter"
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

login_status=$?

if [ $login_status -eq 0 ]; then
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "✅ LOGIN COMPLETADO"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    echo "📋 Próximo paso:"
    echo "   ./paso3-verificar-acceso.sh"
    echo ""
else
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "❌ ERROR EN EL LOGIN"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    echo "Si hubo un error, puedes intentar de nuevo ejecutando:"
    echo "   ./paso2-login-simple.sh"
    echo ""
    exit 1
fi

