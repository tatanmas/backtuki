#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════════
# 🔐 CLOUDFLARE TUNNEL - SETUP PARA TUKI EN DAKO
# ═══════════════════════════════════════════════════════════════════════════════
# Este script instala y configura Cloudflare Tunnel para:
# - SSL automático end-to-end
# - No exponer IP pública
# - No necesitar IP estática (mejor que DuckDNS)
# ═══════════════════════════════════════════════════════════════════════════════

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}🔐 CLOUDFLARE TUNNEL - SETUP PARA TUKI${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 1: Instalar cloudflared
# ═══════════════════════════════════════════════════════════════════════════════
echo -e "${YELLOW}📦 Paso 1: Instalando cloudflared...${NC}"

if command -v cloudflared &> /dev/null; then
    echo -e "${GREEN}   ✅ cloudflared ya está instalado: $(cloudflared --version)${NC}"
else
    echo "   Descargando cloudflared..."
    
    # Detectar arquitectura
    ARCH=$(uname -m)
    if [ "$ARCH" = "x86_64" ]; then
        CLOUDFLARED_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
    elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
        CLOUDFLARED_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
    else
        echo -e "${RED}   ❌ Arquitectura no soportada: $ARCH${NC}"
        exit 1
    fi
    
    curl -L "$CLOUDFLARED_URL" -o /tmp/cloudflared
    chmod +x /tmp/cloudflared
    sudo mv /tmp/cloudflared /usr/local/bin/cloudflared
    
    echo -e "${GREEN}   ✅ cloudflared instalado: $(cloudflared --version)${NC}"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 2: Login en Cloudflare
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}🔑 Paso 2: Autenticación con Cloudflare...${NC}"

CLOUDFLARED_DIR="$HOME/.cloudflared"
mkdir -p "$CLOUDFLARED_DIR"

if [ -f "$CLOUDFLARED_DIR/cert.pem" ]; then
    echo -e "${GREEN}   ✅ Ya estás autenticado con Cloudflare${NC}"
else
    echo ""
    echo -e "${BLUE}   ⚠️  Se abrirá un navegador (o te dará una URL).${NC}"
    echo -e "${BLUE}   📝 Selecciona tu dominio 'tuki.cl' cuando te lo pida.${NC}"
    echo ""
    read -p "   Presiona ENTER para continuar..."
    
    cloudflared tunnel login
    
    if [ -f "$CLOUDFLARED_DIR/cert.pem" ]; then
        echo -e "${GREEN}   ✅ Autenticación exitosa${NC}"
    else
        echo -e "${RED}   ❌ Error en autenticación. Intenta de nuevo.${NC}"
        exit 1
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 3: Crear Tunnel
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}🚇 Paso 3: Creando tunnel...${NC}"

TUNNEL_NAME="tuki-production"

# Verificar si el tunnel ya existe
if cloudflared tunnel list | grep -q "$TUNNEL_NAME"; then
    echo -e "${GREEN}   ✅ Tunnel '$TUNNEL_NAME' ya existe${NC}"
    TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')
else
    echo "   Creando tunnel '$TUNNEL_NAME'..."
    cloudflared tunnel create "$TUNNEL_NAME"
    TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')
    echo -e "${GREEN}   ✅ Tunnel creado con ID: $TUNNEL_ID${NC}"
fi

# Obtener el ID del tunnel
TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')
echo "   📍 Tunnel ID: $TUNNEL_ID"

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 4: Configurar rutas DNS
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}🌐 Paso 4: Configurando DNS...${NC}"

# Configurar DNS para tuki.cl
echo "   Configurando tuki.cl..."
cloudflared tunnel route dns "$TUNNEL_NAME" tuki.cl 2>/dev/null || echo "   ⚠️ tuki.cl ya configurado o error (verificar en Cloudflare)"

echo "   Configurando www.tuki.cl..."
cloudflared tunnel route dns "$TUNNEL_NAME" www.tuki.cl 2>/dev/null || echo "   ⚠️ www.tuki.cl ya configurado o error"

echo "   Configurando api.tuki.cl..."
cloudflared tunnel route dns "$TUNNEL_NAME" api.tuki.cl 2>/dev/null || echo "   ⚠️ api.tuki.cl ya configurado o error"

echo "   Configurando tuki.live..."
cloudflared tunnel route dns "$TUNNEL_NAME" tuki.live 2>/dev/null || echo "   ⚠️ tuki.live (zona debe estar en este Cloudflare account)"
echo "   Configurando www.tuki.live..."
cloudflared tunnel route dns "$TUNNEL_NAME" www.tuki.live 2>/dev/null || echo "   ⚠️ www.tuki.live ya configurado o error"
echo "   Configurando api.tuki.live..."
cloudflared tunnel route dns "$TUNNEL_NAME" api.tuki.live 2>/dev/null || echo "   ⚠️ api.tuki.live ya configurado o error"

echo -e "${GREEN}   ✅ DNS configurado${NC}"

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 5: Crear archivo de configuración
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}📝 Paso 5: Creando configuración del tunnel...${NC}"

# Buscar el archivo de credenciales
CRED_FILE=$(ls "$CLOUDFLARED_DIR"/*.json 2>/dev/null | grep -v cert | head -1)
if [ -z "$CRED_FILE" ]; then
    CRED_FILE="$CLOUDFLARED_DIR/$TUNNEL_ID.json"
fi

cat > "$CLOUDFLARED_DIR/config.yml" << EOF
# Cloudflare Tunnel Configuration for Tuki
tunnel: $TUNNEL_ID
credentials-file: $CRED_FILE

# Configuración de ingress (rutas)
ingress:
  # API Backend - 127.0.0.1 evita 502 por IPv6 (localhost puede resolverse a ::1)
  - hostname: api.tuki.cl
    service: http://127.0.0.1:8000
    originRequest:
      noTLSVerify: true
  - hostname: api.tuki.live
    service: http://127.0.0.1:8000
    originRequest:
      noTLSVerify: true
  
  # Frontend principal - tuki.cl y www.tuki.cl
  - hostname: tuki.cl
    service: http://127.0.0.1:80
    originRequest:
      noTLSVerify: true
  
  - hostname: www.tuki.cl
    service: http://127.0.0.1:80
    originRequest:
      noTLSVerify: true
  
  # tuki.live (evita error 525 si DNS apunta al túnel)
  - hostname: tuki.live
    service: http://127.0.0.1:80
    originRequest:
      noTLSVerify: true
  
  - hostname: www.tuki.live
    service: http://127.0.0.1:80
    originRequest:
      noTLSVerify: true
  
  # Catch-all (requerido)
  - service: http_status:404
EOF

echo -e "${GREEN}   ✅ Configuración creada en $CLOUDFLARED_DIR/config.yml${NC}"

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 6: Probar tunnel
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}🧪 Paso 6: Probando tunnel...${NC}"
echo ""
echo "   Iniciando tunnel en modo test (Ctrl+C para detener)..."
echo "   Verifica que https://tuki.cl funcione en tu navegador"
echo ""

timeout 30 cloudflared tunnel run "$TUNNEL_NAME" || true

echo ""
echo -e "${GREEN}   ✅ Test completado${NC}"

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 7: Instalar como servicio systemd
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}⚙️ Paso 7: Instalando como servicio del sistema...${NC}"

# Crear servicio systemd
sudo tee /etc/systemd/system/cloudflared-tuki.service > /dev/null << EOF
[Unit]
Description=Cloudflare Tunnel for Tuki
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=$USER
ExecStart=/usr/local/bin/cloudflared tunnel --config $CLOUDFLARED_DIR/config.yml run $TUNNEL_NAME
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Recargar systemd
sudo systemctl daemon-reload

# Habilitar e iniciar servicio
sudo systemctl enable cloudflared-tuki
sudo systemctl start cloudflared-tuki

# Verificar estado
sleep 3
if sudo systemctl is-active --quiet cloudflared-tuki; then
    echo -e "${GREEN}   ✅ Servicio cloudflared-tuki corriendo${NC}"
else
    echo -e "${RED}   ❌ Error iniciando servicio. Verificar con:${NC}"
    echo "      sudo journalctl -u cloudflared-tuki -f"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# RESUMEN FINAL
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ CLOUDFLARE TUNNEL INSTALADO EXITOSAMENTE${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "🌐 ${GREEN}URLs con HTTPS:${NC}"
echo "   • Frontend:     https://tuki.cl"
echo "   • Frontend:     https://www.tuki.cl"
echo "   • API:          https://api.tuki.cl/api/v1/"
echo "   • Admin:        https://tuki.cl/admin/"
echo ""
echo -e "📋 ${YELLOW}Comandos útiles:${NC}"
echo "   • Ver estado:   sudo systemctl status cloudflared-tuki"
echo "   • Ver logs:     sudo journalctl -u cloudflared-tuki -f"
echo "   • Reiniciar:    sudo systemctl restart cloudflared-tuki"
echo "   • Detener:      sudo systemctl stop cloudflared-tuki"
echo ""
echo -e "⚠️  ${YELLOW}IMPORTANTE:${NC}"
echo "   1. Ve a Cloudflare Dashboard → SSL/TLS → pon 'Full' o 'Full (strict)'"
echo "   2. En DNS, verifica que tuki.cl tenga un registro CNAME apuntando al tunnel"
echo "   3. Elimina los registros A viejos que apuntaban a IPs de GCP"
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
