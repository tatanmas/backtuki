#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════════
# 🤖 CREAR USUARIO CLOUDBOT (EVA) EN DAKO
# ═══════════════════════════════════════════════════════════════════════════════
# Conecta por SSH a Dako y ejecuta en el backend:
#   python manage.py create_cloudbot_user --email ... --password ...
# Así Eva puede autenticarse vía JWT contra el API de Tuki.
#
# Uso (desde tu Mac, con SSH key a Dako):
#   cd backtuki && ./create-cloudbot-user-dako.sh
#   ./create-cloudbot-user-dako.sh --email eva-cloudbot@tuki.cl --password "TuPasswordSegura"
#   ./create-cloudbot-user-dako.sh --email eva-cloudbot@tuki.cl --password "NuevaPassword" --update-password   # si el usuario ya existe
#   CLOUDBOT_EMAIL=eva@tuki.cl CLOUDBOT_PASSWORD="xxx" ./create-cloudbot-user-dako.sh
# ═══════════════════════════════════════════════════════════════════════════════

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DAKO_HOST="${DAKO_HOST:-tukitickets.duckdns.org}"
DAKO_PORT="${DAKO_PORT:-2222}"
DAKO_USER="${DAKO_USER:-tatan}"
DAKO_PATH="${DAKO_PATH:-/home/tatan/Desktop/tuki}"

# Email y password: argumentos, env o prompt
UPDATE_PASSWORD=false
for i in "$@"; do
    [ "$i" = "--update-password" ] && UPDATE_PASSWORD=true
done
if [ -n "$1" ] && [ "$1" = "--email" ] && [ -n "$2" ]; then
    CLOUDBOT_EMAIL="$2"
    [ "$3" = "--password" ] && [ -n "$4" ] && CLOUDBOT_PASSWORD="$4"
fi
[ -z "$CLOUDBOT_EMAIL" ] && CLOUDBOT_EMAIL="${CLOUDBOT_EMAIL:-}"
[ -z "$CLOUDBOT_PASSWORD" ] && CLOUDBOT_PASSWORD="${CLOUDBOT_PASSWORD:-}"

if [ -z "$CLOUDBOT_EMAIL" ]; then
    echo -e "${YELLOW}Email del usuario Cloudbot (ej. eva-cloudbot@tuki.cl):${NC}"
    read -r CLOUDBOT_EMAIL
fi
if [ -z "$CLOUDBOT_PASSWORD" ]; then
    echo -e "${YELLOW}Contraseña (no se mostrará):${NC}"
    read -rs CLOUDBOT_PASSWORD
    echo ""
fi

if [ -z "$CLOUDBOT_EMAIL" ] || [ -z "$CLOUDBOT_PASSWORD" ]; then
    echo -e "${RED}❌ Faltan email o contraseña.${NC}"
    exit 1
fi

# Escapar para uso dentro de comillas simples en el remoto
escape_single() { printf '%s\n' "$1" | sed "s/'/'\\\\''/g"; }
ESC_EMAIL=$(escape_single "$CLOUDBOT_EMAIL")
ESC_PASS=$(escape_single "$CLOUDBOT_PASSWORD")

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}🤖 Crear usuario Cloudbot (Eva) en el backend en Dako${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "   Host: ${YELLOW}${DAKO_USER}@${DAKO_HOST}:${DAKO_PORT}${NC}"
echo -e "   Email: ${YELLOW}${CLOUDBOT_EMAIL}${NC}"
echo ""

echo -e "${YELLOW}🔌 Conectando por SSH y ejecutando create_cloudbot_user en el backend...${NC}"
# --entrypoint "" evita que corra el entrypoint del contenedor (migrate, collectstatic, gunicorn)
# y así se ejecuta solo: python manage.py create_cloudbot_user
EXTRA_ARGS=""
[ "$UPDATE_PASSWORD" = true ] && EXTRA_ARGS="--update-password"
if ! ssh -p "$DAKO_PORT" -o ConnectTimeout=15 "$DAKO_USER@$DAKO_HOST" \
    "export CLOUDBOT_EMAIL='$ESC_EMAIL' CLOUDBOT_PASSWORD='$ESC_PASS'; cd $DAKO_PATH && docker compose run --rm --entrypoint '' -e CLOUDBOT_EMAIL -e CLOUDBOT_PASSWORD tuki-backend-a python manage.py create_cloudbot_user $EXTRA_ARGS"; then
    echo ""
    echo -e "${RED}❌ Error al conectar o al ejecutar el comando.${NC}"
    echo -e "   Verifica: servidor encendido, clave SSH, que en Dako exista $DAKO_PATH y docker compose.${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ Usuario Cloudbot creado (o ya existía). Configura en el Cloudbot: TUKI_API_BASE_URL, TUKI_EVA_EMAIL, TUKI_EVA_PASSWORD.${NC}"
echo ""
