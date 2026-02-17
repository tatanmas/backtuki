#!/bin/bash
# Instala el servicio systemd que levanta el stack Tuki al arrancar Dako.
# Ejecutar en Dako, desde el directorio del repo (ej. ~/Desktop/tuki).
set -e
TUKI_DIR=$(pwd)
if [ ! -f "$TUKI_DIR/backtuki/docker-compose.dako.yml" ]; then
    echo "❌ Ejecuta este script desde la raíz del repo Tuki (donde está backtuki/)."
    exit 1
fi
SERVICE_SRC="$TUKI_DIR/backtuki/systemd/tuki-dako-boot.service"
SERVICE_DEST="/etc/systemd/system/tuki-dako-boot.service"
sudo cp "$SERVICE_SRC" "$SERVICE_DEST"
sudo sed -i "s|/home/tatan/Desktop/tuki|$TUKI_DIR|g" "$SERVICE_DEST"
sudo systemctl daemon-reload
sudo systemctl enable tuki-dako-boot
echo "✅ Servicio instalado y habilitado. En el próximo arranque se levantará el stack."
echo "   Para levantar ahora: sudo systemctl start tuki-dako-boot"
echo "   Estado: sudo systemctl status tuki-dako-boot"
