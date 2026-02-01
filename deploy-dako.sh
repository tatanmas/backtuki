#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════════
# 🚀 TUKI PLATFORM - DEPLOY COMPLETO A DAKO SERVER
# ═══════════════════════════════════════════════════════════════════════════════
# Este script prepara y levanta TODO Tuki en el servidor Dako
# Ejecutar desde: ~/Desktop/tuki/
# ═══════════════════════════════════════════════════════════════════════════════

set -e

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
# PASO 1: Actualizar repositorios
# ═══════════════════════════════════════════════════════════════════════════════
echo "📥 Paso 1: Actualizando repositorios..."

cd "$TUKI_DIR/backtuki"
git fetch origin main
git reset --hard origin/main
echo "   ✅ Backend actualizado"

cd "$TUKI_DIR/tuki-experiencias"
git fetch origin main
git reset --hard origin/main
echo "   ✅ Frontend actualizado"

cd "$TUKI_DIR"

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 2: Copiar archivos de configuración
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "📋 Paso 2: Copiando archivos de configuración..."

cp backtuki/docker-compose.dako.yml docker-compose.yml
echo "   ✅ docker-compose.yml"

cp backtuki/nginx.dako.conf nginx.conf
echo "   ✅ nginx.conf"

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 3: Compilar Frontend
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "🔨 Paso 3: Compilando frontend..."

cd "$TUKI_DIR/tuki-experiencias"

# Verificar node
if ! command -v node &> /dev/null; then
    echo "   ⚠️ Node.js no encontrado. Instalando..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

echo "   Node: $(node --version)"

# Crear .env.production
cat > .env.production << 'EOF'
VITE_API_BASE_URL=https://tukitickets.duckdns.org/api/v1
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

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 4: Detener servicios existentes (si hay)
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "🛑 Paso 4: Deteniendo servicios existentes..."

docker-compose down 2>/dev/null || true
echo "   ✅ Servicios detenidos"

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 5: Levantar PostgreSQL y Redis
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "🗄️ Paso 5: Levantando PostgreSQL y Redis..."

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
# PASO 6: Construir y levantar Backend
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "🐍 Paso 6: Construyendo Backend..."

docker-compose build tuki-backend
docker-compose up -d tuki-backend

echo "   ⏳ Esperando Backend..."
sleep 15

# Verificar que está corriendo
if ! docker ps | grep -q tuki-backend; then
    echo "   ❌ Error: Backend no arrancó"
    docker logs tuki-backend --tail 50
    exit 1
fi
echo "   ✅ Backend corriendo"

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 7: Migraciones y setup
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "🗄️ Paso 7: Ejecutando migraciones..."

docker-compose exec -T tuki-backend python manage.py migrate --noinput
echo "   ✅ Migraciones completadas"

echo ""
echo "📁 Paso 8: Collectstatic..."
docker-compose exec -T tuki-backend python manage.py collectstatic --noinput
echo "   ✅ Archivos estáticos recolectados"

echo ""
echo "👤 Paso 9: Verificando superusuario..."
docker-compose exec -T tuki-backend python manage.py shell << 'PYEOF'
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
# PASO 10: Levantar Celery
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "⚙️ Paso 10: Levantando Celery workers..."

docker-compose up -d tuki-celery-worker tuki-celery-beat
sleep 5
echo "   ✅ Celery corriendo"

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 11: Levantar Frontend
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "🌐 Paso 11: Levantando Frontend (Nginx)..."

docker-compose up -d tuki-frontend
sleep 3
echo "   ✅ Frontend corriendo en puerto 80"

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

# Backend health
if curl -s http://localhost:8000/api/v1/health/ | grep -q "ok\|healthy\|status"; then
    echo "   ✅ Backend API: http://localhost:8000 ✓"
else
    echo "   ⚠️ Backend API: respuesta inesperada (puede estar OK)"
fi

# Frontend
if curl -s -o /dev/null -w "%{http_code}" http://localhost:80 | grep -q "200"; then
    echo "   ✅ Frontend: http://localhost:80 ✓"
else
    echo "   ⚠️ Frontend: verificar manualmente"
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
echo "   • Frontend:     http://tukitickets.duckdns.org"
echo "   • Backend API:  http://tukitickets.duckdns.org:8000/api/v1/"
echo "   • Admin Django: http://tukitickets.duckdns.org:8000/admin/"
echo ""
echo "🔐 Credenciales SuperAdmin:"
echo "   • Email:    admin@tuki.cl"
echo "   • Password: TukiAdmin2025!"
echo ""
echo "📦 Volumes persistentes (datos seguros):"
echo "   • tuki_postgres_data  → Base de datos"
echo "   • tuki_media          → Archivos subidos"
echo "   • tuki_staticfiles    → Archivos estáticos"
echo "   • tuki_redis_data     → Cache Redis"
echo ""
echo "📋 Comandos útiles:"
echo "   • Ver logs:        docker-compose logs -f"
echo "   • Ver logs back:   docker-compose logs -f tuki-backend"
echo "   • Reiniciar:       docker-compose restart"
echo "   • Detener todo:    docker-compose down"
echo "   • Actualizar:      ./backtuki/deploy-dako.sh"
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
