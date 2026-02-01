#!/bin/bash
# Script para analizar el servidor local y ver qué tenemos disponible

SSH_HOST="tukitickets.duckdns.org"
SSH_PORT="2222"
SSH_USER="tatan"

echo "🔍 Analizando servidor local..."
echo "================================"

# Crear comando SSH base
SSH_CMD="ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST}"

echo ""
echo "=== SISTEMA OPERATIVO ==="
$SSH_CMD "cat /etc/os-release | grep PRETTY_NAME"

echo ""
echo "=== RECURSOS ==="
$SSH_CMD "echo 'CPU Cores:' && nproc && echo 'RAM Total:' && free -h | grep Mem | awk '{print \$2}' && echo 'Disk Space:' && df -h / | tail -1"

echo ""
echo "=== DOCKER INSTALADO ==="
$SSH_CMD "docker --version && docker-compose --version"

echo ""
echo "=== PUERTOS EN USO ==="
echo "Puertos actualmente ocupados:"
$SSH_CMD "netstat -tln 2>/dev/null | grep LISTEN || ss -tln | grep LISTEN"

echo ""
echo "=== SERVICIOS DOCKER ACTUALES ==="
$SSH_CMD "docker ps --format 'table {{.Names}}\t{{.Ports}}'"

echo ""
echo "=== ESPACIO EN DISCO ==="
$SSH_CMD "df -h | grep -E '^/dev/|Filesystem'"

echo ""
echo "=== DIRECTORIO HOME ==="
$SSH_CMD "pwd && ls -lah"

echo ""
echo "✅ Análisis completado"

