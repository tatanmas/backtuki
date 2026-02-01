#!/bin/bash

# 🔐 PASO 2: LOGIN GCLOUD (MANUAL)
# Este script te guía para hacer login en gcloud

SSH_HOST="tukitickets.duckdns.org"
SSH_PORT="2222"
SSH_USER="tatan"
SSH_PASS="rollolupita"

echo "🔐 PASO 2: CONFIGURAR CREDENCIALES GCP"
echo "======================================="
echo ""
echo "Vamos a hacer login en gcloud. Necesitarás:"
echo "  1. Abrir una URL en tu navegador"
echo "  2. Iniciar sesión con: tecnologia@tuki.cl"
echo "  3. Copiar el código de verificación"
echo ""
read -p "Presiona Enter para continuar..."

# Conectar y ejecutar login
expect << 'EXPECT_SCRIPT'
set timeout 300
spawn ssh -o StrictHostKeyChecking=no -p 2222 tatan@tukitickets.duckdns.org
expect "password:"
send "rollolupita\r"
expect "$ "
send "export PATH=\$PATH:\$HOME/google-cloud-sdk/bin\r"
expect "$ "
send "gcloud auth login --no-launch-browser\r"
expect {
    "Enter verification code:" {
        puts "\n\n"
        puts "═══════════════════════════════════════════════════════════"
        puts "🔐 INSTRUCCIONES:"
        puts "═══════════════════════════════════════════════════════════"
        puts ""
        puts "1. Copia la URL que aparece arriba"
        puts "2. Ábrela en tu navegador"
        puts "3. Inicia sesión con: tecnologia@tuki.cl"
        puts "4. Contraseña: >2gfbinrlFQ6"
        puts "5. Copia el código de verificación"
        puts "6. Pégalo aquí abajo y presiona Enter"
        puts ""
        puts "═══════════════════════════════════════════════════════════"
        puts ""
        interact
    }
    "You are now logged in" {
        puts "\n✅ Login exitoso\n"
    }
    timeout {
        puts "\n❌ Timeout\n"
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

echo ""
echo "✅ Si el login fue exitoso, continúa con el siguiente paso"
echo "   Ejecutar: ./paso3-verificar-acceso.sh"

