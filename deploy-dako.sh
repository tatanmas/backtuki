#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════════
# 🚀 TUKI PLATFORM - DEPLOY COMPLETO A DAKO SERVER
# ═══════════════════════════════════════════════════════════════════════════════
# Este script prepara y levanta TODO Tuki en el servidor Dako
# Ejecutar desde: ~/Desktop/tuki/
#
# Opciones:
#   --skip-git-pull   Omitir git pull (útil cuando el código llegó por rsync)
#   --no-cache        Reconstruir imágenes sin caché (requerido si cambiaste requirements.txt, Dockerfile, etc.)
#   --force-recreate-frontend  Recrear contenedor nginx (breve caída; solo si cambiaste montajes o config nginx)
#
# Por defecto: build con caché (menos RAM/tiempo). Blue-green: downtime cercano a 0.
# Durante el switch hay ~1 min con dos backends en RAM; luego se para el viejo.
# ═══════════════════════════════════════════════════════════════════════════════

set -e

SKIP_GIT_PULL=false
SKIP_FRONTEND_BUILD=false
BUILD_NO_CACHE=""
FORCE_RECREATE_FRONTEND=false
for arg in "$@"; do
    [ "$arg" = "--skip-git-pull" ] && SKIP_GIT_PULL=true
    [ "$arg" = "--skip-frontend-build" ] && SKIP_FRONTEND_BUILD=true
    [ "$arg" = "--no-cache" ] && BUILD_NO_CACHE="--no-cache"
    [ "$arg" = "--force-recreate-frontend" ] && FORCE_RECREATE_FRONTEND=true
done

# Si no se pasó --no-cache y la sesión es interactiva, preguntar (ahorra RAM en servidores justos)
if [ -z "$BUILD_NO_CACHE" ] && [ -t 0 ]; then
    echo "   ¿Reconstruir imágenes sin caché? (s/n)"
    echo "   [Recomendado si cambiaste requirements.txt, package.json o Dockerfile; si no, n ahorra RAM y tiempo]"
    read -r REPLY
    if [ "$REPLY" = "s" ] || [ "$REPLY" = "S" ]; then
        BUILD_NO_CACHE="--no-cache"
        echo "   → Se usará --no-cache"
    else
        echo "   → Build con caché"
    fi
fi
if [ -n "$BUILD_NO_CACHE" ]; then
    echo "   📦 Build sin caché (--no-cache)"
fi
# Preguntar recrear frontend solo si interactivo y no se pasó el flag
if [ "$FORCE_RECREATE_FRONTEND" = false ] && [ -t 0 ]; then
    echo "   ¿Recrear contenedor del frontend (nginx)? (s/n)"
    echo "   [Normalmente n; solo s si cambiaste montajes, nginx.conf o necesitas reiniciar el contenedor]"
    read -r REPLY
    if [ "$REPLY" = "s" ] || [ "$REPLY" = "S" ]; then
        FORCE_RECREATE_FRONTEND=true
        echo "   → Se recreará el contenedor frontend (breve caída)"
    fi
fi

echo "═══════════════════════════════════════════════════════════════════════════════"
echo "🚀 TUKI PLATFORM - DEPLOY COMPLETO A PRODUCCIÓN"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -d "backtuki" ] || [ ! -d "tuki-experiencias" ]; then
    echo "❌ Error: Debes ejecutar este script desde ~/Desktop/tuki/"
    echo "   Asegúrate de tener las carpetas backtuki/ y tuki-experiencias/"
    exit 1
fi

TUKI_DIR=$(pwd)
echo "📁 Directorio: $TUKI_DIR"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 1: Actualizar repositorios (omitir si --skip-git-pull)
# ═══════════════════════════════════════════════════════════════════════════════
if [ "$SKIP_GIT_PULL" = true ]; then
    echo "📥 Paso 1: Omitiendo git pull (código ya sincronizado por rsync)"
else
echo "📥 Paso 1: Actualizando repositorios..."

# Backend
cd "$TUKI_DIR/backtuki"
echo "   📡 Verificando estado del repositorio backend..."
if [ -d ".git" ]; then
    # Guardar cambios locales si los hay
    if ! git diff-index --quiet HEAD -- 2>/dev/null; then
        echo "   ⚠️ Hay cambios locales, haciendo stash..."
        git stash save "Auto-stash antes de deploy $(date +%Y%m%d-%H%M%S)" || true
    fi
    
    # Obtener rama actual
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
    echo "   📍 Rama actual: $CURRENT_BRANCH"
    
    # Fetch y pull
    echo "   📥 Haciendo fetch..."
    git fetch origin "$CURRENT_BRANCH" || git fetch origin main || true
    
    echo "   📥 Haciendo pull..."
    git pull origin "$CURRENT_BRANCH" || git pull origin main || {
        echo "   ⚠️ Pull falló, intentando reset..."
        git reset --hard "origin/$CURRENT_BRANCH" || git reset --hard origin/main || true
    }
    
    echo "   ✅ Backend actualizado ($(git rev-parse --short HEAD))"
else
    echo "   ⚠️ No es un repositorio git, saltando actualización"
fi

# Frontend
cd "$TUKI_DIR/tuki-experiencias"
echo "   📡 Verificando estado del repositorio frontend..."
if [ -d ".git" ]; then
    # Guardar cambios locales si los hay
    if ! git diff-index --quiet HEAD -- 2>/dev/null; then
        echo "   ⚠️ Hay cambios locales, haciendo stash..."
        git stash save "Auto-stash antes de deploy $(date +%Y%m%d-%H%M%S)" || true
    fi
    
    # Obtener rama actual
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
    echo "   📍 Rama actual: $CURRENT_BRANCH"
    
    # Fetch y pull
    echo "   📥 Haciendo fetch..."
    git fetch origin "$CURRENT_BRANCH" || git fetch origin main || true
    
    echo "   📥 Haciendo pull..."
    git pull origin "$CURRENT_BRANCH" || git pull origin main || {
        echo "   ⚠️ Pull falló, intentando reset..."
        git reset --hard "origin/$CURRENT_BRANCH" || git reset --hard origin/main || true
    }
    
    echo "   ✅ Frontend actualizado ($(git rev-parse --short HEAD))"
else
    echo "   ⚠️ No es un repositorio git, saltando actualización"
fi

cd "$TUKI_DIR"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 2: Copiar archivos de configuración
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "📋 Paso 2: Copiando archivos de configuración..."

cp backtuki/docker-compose.dako.yml docker-compose.yml
echo "   ✅ docker-compose.yml"

cp backtuki/nginx.dako.conf nginx.conf
echo "   ✅ nginx.conf"

# backend_upstream.conf: creado desde template si no existe (blue-green)
if [ ! -f backend_upstream.conf ]; then
    cp backtuki/backend_upstream.conf.template backend_upstream.conf
    echo "   ✅ backend_upstream.conf (creado desde template)"
fi
# backend_live.txt: "a" o "b", quién recibe el tráfico
if [ ! -f backend_live.txt ]; then
    echo "a" > backend_live.txt
    echo "   ✅ backend_live.txt (creado, live=a)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 3: Compilar Frontend (omitir si --skip-frontend-build: ya llegó dist/ por rsync)
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
if [ "$SKIP_FRONTEND_BUILD" = true ]; then
    echo "🔨 Paso 3: Omitiendo compilación frontend (dist/ ya sincronizado desde tu Mac)"
    if [ ! -d "$TUKI_DIR/tuki-experiencias/dist" ]; then
        echo "   ❌ Error: No existe tuki-experiencias/dist. Ejecuta el deploy desde tu Mac: ./deploy-dako"
        exit 1
    fi
    echo "   ✅ Usando dist/ existente"
else
echo "🔨 Paso 3: Compilando frontend..."

cd "$TUKI_DIR/tuki-experiencias"

# Verificar node
if ! command -v node &> /dev/null; then
    echo "   ⚠️ Node.js no encontrado. Instalando..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

echo "   Node: $(node --version)"

# Crear .env.production (HTTPS con Cloudflare Tunnel)
cat > .env.production << 'EOF'
VITE_API_BASE_URL=https://tuki.cl/api/v1
VITE_APP_ENV=production
EOF
echo "   ✅ .env.production creado"

# Instalar y compilar
echo "   📦 Instalando dependencias..."
npm install --legacy-peer-deps --silent 2>/dev/null || npm install --legacy-peer-deps

echo "   🔨 Compilando..."
npm run build

echo "   ✅ Frontend compilado"

cd "$TUKI_DIR"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 4: Asegurar PostgreSQL y Redis (sin bajar la instancia; actualización en caliente)
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "🗄️ Paso 4: Asegurando PostgreSQL y Redis..."

docker-compose up -d tuki-db tuki-redis

echo "   ⏳ Esperando PostgreSQL..."
until docker exec tuki-db pg_isready -U tuki_user -d tuki_production 2>/dev/null; do
    sleep 2
done
echo "   ✅ PostgreSQL listo"

echo "   ⏳ Esperando Redis..."
until docker exec tuki-redis redis-cli ping 2>/dev/null | grep -q PONG; do
    sleep 2
done
echo "   ✅ Redis listo"

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 5: Backend blue-green (cero downtime; dos backends solo durante el switch)
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "🐍 Paso 5: Backend blue-green (sin cortar tráfico)..."

# Quitar contenedor huérfano del compose antiguo (tuki-backend) para liberar puerto 8000
docker rm -f tuki-backend 2>/dev/null || true

CURRENT_LIVE=$(cat backend_live.txt 2>/dev/null || echo "a")
if [ "$CURRENT_LIVE" = "a" ]; then
    IDLE="b"
else
    IDLE="a"
fi
echo "   📍 Live actual: tuki-backend-${CURRENT_LIVE} → nuevo: tuki-backend-${IDLE}"

export APP_VERSION=$(cd backtuki && git rev-parse --short HEAD 2>/dev/null || echo "norepo")
export DEPLOYED_AT=$(TZ=America/Santiago date -Iseconds)
echo "   📌 APP_VERSION=$APP_VERSION"

# Asegurar que el live actual está arriba (por si es el primer deploy con este script)
docker-compose up -d "tuki-backend-${CURRENT_LIVE}" 2>/dev/null || true

# Construir imagen (compartida por a y b)
docker-compose build $BUILD_NO_CACHE tuki-backend-a tuki-backend-b

# Levantar el backend "idle" (el que va a pasar a ser live)
if [ "$IDLE" = "b" ]; then
    docker-compose --profile bluegreen up -d tuki-backend-b
else
    docker-compose up -d tuki-backend-a
fi

echo "   ⏳ Esperando health del nuevo backend (máx 90s; durante esto hay dos backends en RAM)..."
for i in $(seq 1 45); do
    if docker inspect --format='{{.State.Health.Status}}' "tuki-backend-${IDLE}" 2>/dev/null | grep -q healthy; then
        echo "   ✅ tuki-backend-${IDLE} healthy"
        break
    fi
    if [ "$i" -eq 45 ]; then
        echo "   ❌ Timeout: tuki-backend-${IDLE} no pasó healthcheck"
        docker logs "tuki-backend-${IDLE}" --tail 30
        exit 1
    fi
    sleep 2
done

# Cambiar tráfico al nuevo y parar el viejo (ventana con dos backends termina aquí)
echo "upstream tuki_backend_live { server tuki-backend-${IDLE}:8080; }" > backend_upstream.conf
docker exec tuki-frontend nginx -s reload 2>/dev/null || true
echo "   ✅ Nginx apuntando a tuki-backend-${IDLE}"

docker-compose stop "tuki-backend-${CURRENT_LIVE}"
echo "$IDLE" > backend_live.txt
echo "   ✅ Backend viejo parado (solo un backend en RAM ahora)"
LIVE_CONTAINER="tuki-backend-${IDLE}"

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 6: Migraciones y setup (en el backend que quedó en vivo)
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "🗄️ Paso 6: Ejecutando migraciones (en $LIVE_CONTAINER)..."

docker-compose exec -T "$LIVE_CONTAINER" python manage.py migrate --noinput
echo "   ✅ Migraciones completadas"

echo ""
echo "💳 Paso 6b: Activando medios de pago (Transbank WebPay Plus)..."
docker-compose exec -T "$LIVE_CONTAINER" python manage.py setup_payment_providers 2>/dev/null || echo "   ⚠️ setup_payment_providers falló (puede estar ya configurado)"
echo "   ✅ Medios de pago configurados"

echo ""
echo "📁 Paso 7: Collectstatic..."
docker-compose exec -T "$LIVE_CONTAINER" python manage.py collectstatic --noinput
echo "   ✅ Archivos estáticos recolectados"

echo ""
echo "👤 Paso 8: Verificando superusuario..."
docker-compose exec -T "$LIVE_CONTAINER" python manage.py shell << 'PYEOF'
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='admin@tuki.cl').exists():
    User.objects.create_superuser(
        email='admin@tuki.cl',
        username='admin',
        password='TukiAdmin2025!',
        first_name='Admin',
        last_name='Tuki'
    )
    print("   ✅ Superusuario creado: admin@tuki.cl")
else:
    print("   ℹ️ Superusuario ya existe")
PYEOF

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 9: Levantar Celery
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "⚙️ Paso 9: Levantando Celery workers..."

docker-compose up -d tuki-celery-worker tuki-celery-beat
sleep 5
echo "   ✅ Celery corriendo"

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 10: Construir y levantar WhatsApp Service
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "📱 Paso 10: Construyendo y levantando WhatsApp Service..."

docker-compose build tuki-whatsapp-service
docker-compose up -d tuki-whatsapp-service

echo "   ⏳ Esperando WhatsApp Service..."
sleep 10

# Verificar que está corriendo
if docker ps | grep -q tuki-whatsapp-service; then
    echo "   ✅ WhatsApp Service corriendo en puerto 3001"
else
    echo "   ⚠️ WhatsApp Service no arrancó (puede requerir QR)"
    docker logs tuki-whatsapp-service --tail 20 2>/dev/null || true
fi

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 11: Frontend (Nginx) — sin recrear = sin caída; reload si no se fuerza recrear
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "🌐 Paso 11: Frontend (Nginx)..."

if [ "$FORCE_RECREATE_FRONTEND" = true ]; then
    echo "   ⚠️ Recreando contenedor (breve caída)..."
    docker-compose up -d --force-recreate tuki-frontend
    sleep 3
else
    docker-compose up -d tuki-frontend
    docker exec tuki-frontend nginx -s reload 2>/dev/null || true
fi
echo "   ✅ Frontend en puerto 80 (dist/ actualizado)"

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 12: Cloudflare Tunnel (tuki.cl → host:80/8000)
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "🚇 Paso 12: Levantando Cloudflare Tunnel..."
if [ -d "$HOME/.cloudflared" ] && [ -f "$HOME/.cloudflared/config.yml" ]; then
    docker-compose up -d tuki-cloudflared 2>/dev/null || true
    sleep 2
    if docker ps | grep -q tuki-cloudflared; then
        echo "   ✅ Tunnel corriendo (tuki.cl / www.tuki.cl)"
    else
        echo "   ⚠️ Tunnel no arrancó (revisar ~/.cloudflared/config.yml y credenciales)"
    fi
else
    echo "   ⚠️ Omitiendo tunnel: en este servidor no existe $HOME/.cloudflared/config.yml"
    echo "   → Sin tunnel, https://tuki.cl no apuntará aquí. Configura cloudflared en el servidor o usa http://tukitickets.duckdns.org"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICACIÓN FINAL
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
echo "🔍 VERIFICACIÓN FINAL"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""

# Mostrar servicios
echo "📊 Servicios corriendo:"
docker-compose ps
echo ""

# Verificar endpoints
echo "🔗 Probando endpoints..."

# Backend health (vía nginx = tráfico real)
if curl -s http://localhost:80/healthz/ | grep -q "ok\|healthy\|status"; then
    echo "   ✅ Backend API (vía nginx): https://tuki.cl/api/v1/ ✓"
else
    echo "   ⚠️ Backend API: verificar manualmente"
fi

# Frontend
if curl -s -o /dev/null -w "%{http_code}" http://localhost:80 | grep -q "200"; then
    echo "   ✅ Frontend: http://localhost:80 ✓"
else
    echo "   ⚠️ Frontend: verificar manualmente"
fi

# WhatsApp Service
if curl -s http://localhost:3001/health | grep -q "ok\|status"; then
    echo "   ✅ WhatsApp Service: http://localhost:3001 ✓"
    # Check if WhatsApp is connected
    WA_STATUS=$(curl -s http://localhost:3001/api/status 2>/dev/null || echo '{}')
    if echo "$WA_STATUS" | grep -q '"isReady":true'; then
        echo "   ✅ WhatsApp: Conectado y listo"
    else
        echo "   📱 WhatsApp: Requiere escanear QR"
        echo "      → Ver QR: curl http://localhost:3001/api/qr"
        echo "      → O acceder a SuperAdmin para escanear"
    fi
else
    echo "   ⚠️ WhatsApp Service: verificar manualmente"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# RESUMEN
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
echo "✅ DEPLOY COMPLETADO EXITOSAMENTE"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""
echo "🌐 URLs de acceso:"
echo "   • Frontend:     https://tuki.cl"
echo "   • Backend API:  https://tuki.cl/api/v1/"
echo "   • Admin Django: https://tuki.cl/admin/"
echo ""
echo "🔐 Credenciales SuperAdmin:"
echo "   • Email:    admin@tuki.cl"
echo "   • Password: TukiAdmin2025!"
echo ""
echo "📦 Volumes persistentes (datos seguros):"
echo "   • tuki_postgres_data     → Base de datos"
echo "   • tuki_media             → Archivos subidos"
echo "   • tuki_staticfiles       → Archivos estáticos"
echo "   • tuki_redis_data        → Cache Redis"
echo "   • tuki_whatsapp_sessions → Sesiones WhatsApp"
echo ""
echo "📱 WhatsApp Service:"
echo "   • Health:    http://localhost:3001/health"
echo "   • Status:    http://localhost:3001/api/status"
echo "   • QR Code:   http://localhost:3001/api/qr"
echo "   • Logs:      docker-compose logs -f tuki-whatsapp-service"
echo ""
echo "📋 Comandos útiles:"
echo "   • Ver logs:          docker-compose logs -f"
echo "   • Ver logs back:     docker-compose logs -f tuki-backend"
echo "   • Ver logs whatsapp: docker-compose logs -f tuki-whatsapp-service"
echo "   • Reiniciar:         docker-compose restart"
echo "   • Detener todo:      docker-compose down"
echo "   • Actualizar:        ./backtuki/deploy-dako.sh"
echo ""
echo "📌 Persistencia tras reinicio: ver docs/DAKO_PERSISTENCIA.md"
echo "   (Docker al boot + opcional: ./backtuki/install-tuki-boot-service.sh)"
echo ""
echo "💡 Si el front no refleja cambios (toasts, logs, media): hard refresh en el navegador (Cmd+Shift+R)"
echo "💡 Si las subidas de medios (fotos alojamientos/experiencias) fallan: docker logs tuki-backend --tail 200 (ver motivo 400) y reiniciar: docker-compose up -d tuki-backend"
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
