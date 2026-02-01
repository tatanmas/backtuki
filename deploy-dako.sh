#!/bin/bash

# ═══════════════════════════════════════════════════════════════════════════════
# 🚀 TUKI PLATFORM - DEPLOY TO DAKO SERVER
# ═══════════════════════════════════════════════════════════════════════════════
# Este script prepara y levanta Tuki en el servidor Dako
# Ejecutar desde: ~/Desktop/tuki/
# ═══════════════════════════════════════════════════════════════════════════════

set -e

echo "═══════════════════════════════════════════════════════════════════════════════"
echo "🚀 TUKI PLATFORM - DEPLOY TO DAKO"
echo "═══════════════════════════════════════════════════════════════════════════════"

# Verificar que estamos en el directorio correcto
if [ ! -d "backtuki" ] || [ ! -d "tuki-experiencias" ]; then
    echo "❌ Error: Debes ejecutar este script desde ~/Desktop/tuki/"
    echo "   Asegúrate de tener las carpetas backtuki/ y tuki-experiencias/"
    exit 1
fi

echo ""
echo "📁 Directorio actual: $(pwd)"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 1: Copiar archivos de configuración
# ═══════════════════════════════════════════════════════════════════════════════
echo "📋 Paso 1: Copiando archivos de configuración..."

# Copiar docker-compose
cp backtuki/docker-compose.dako.yml docker-compose.yml
echo "   ✅ docker-compose.yml copiado"

# Copiar nginx config
cp backtuki/nginx.dako.conf nginx.conf
echo "   ✅ nginx.conf copiado"

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 2: Compilar Frontend
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "🔨 Paso 2: Compilando frontend..."

cd tuki-experiencias

# Verificar si node está instalado
if ! command -v node &> /dev/null; then
    echo "❌ Node.js no está instalado. Instalando..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

# Verificar versión de node
echo "   Node version: $(node --version)"
echo "   NPM version: $(npm --version)"

# Instalar dependencias
echo "   📦 Instalando dependencias..."
npm install --legacy-peer-deps

# Crear archivo .env para build
echo "   📝 Creando .env para producción..."
cat > .env.production << 'EOF'
VITE_API_BASE_URL=https://tukitickets.duckdns.org/api/v1
VITE_APP_ENV=production
EOF

# Compilar
echo "   🔨 Compilando React app..."
npm run build

echo "   ✅ Frontend compilado en dist/"

cd ..

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 3: Levantar servicios de infraestructura primero
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "🐳 Paso 3: Levantando PostgreSQL y Redis..."

docker-compose up -d tuki-db tuki-redis

echo "   ⏳ Esperando a que PostgreSQL esté listo..."
sleep 10

# Verificar que PostgreSQL está listo
until docker exec tuki-db pg_isready -U tuki_user -d tuki_production; do
    echo "   ⏳ Esperando PostgreSQL..."
    sleep 2
done
echo "   ✅ PostgreSQL listo"

# Verificar Redis
until docker exec tuki-redis redis-cli ping | grep -q PONG; do
    echo "   ⏳ Esperando Redis..."
    sleep 2
done
echo "   ✅ Redis listo"

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 4: Construir y levantar Backend
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "🐍 Paso 4: Construyendo y levantando Backend..."

docker-compose build tuki-backend
docker-compose up -d tuki-backend

echo "   ⏳ Esperando a que Backend esté listo..."
sleep 20

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 5: Ejecutar migraciones
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "🗄️ Paso 5: Ejecutando migraciones de base de datos..."

docker-compose exec -T tuki-backend python manage.py migrate --noinput

echo "   ✅ Migraciones completadas"

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 6: Crear superusuario si no existe
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "👤 Paso 6: Creando superusuario..."

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
    print("✅ Superusuario creado: admin@tuki.cl / TukiAdmin2025!")
else:
    print("ℹ️ Superusuario ya existe")
PYEOF

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 7: Collectstatic
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "📁 Paso 7: Recolectando archivos estáticos..."

docker-compose exec -T tuki-backend python manage.py collectstatic --noinput

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 8: Levantar Celery workers
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "⚙️ Paso 8: Levantando Celery workers..."

docker-compose up -d tuki-celery-worker tuki-celery-beat

# ═══════════════════════════════════════════════════════════════════════════════
# PASO 9: Levantar Frontend
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "🌐 Paso 9: Levantando Frontend (Nginx)..."

docker-compose up -d tuki-frontend

# ═══════════════════════════════════════════════════════════════════════════════
# RESUMEN FINAL
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
echo "✅ DEPLOY COMPLETADO"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""
echo "📊 Estado de los servicios:"
docker-compose ps
echo ""
echo "🌐 URLs de acceso:"
echo "   - Frontend:  http://tukitickets.duckdns.org"
echo "   - Backend:   http://tukitickets.duckdns.org:8000"
echo "   - Admin:     http://tukitickets.duckdns.org/admin/"
echo ""
echo "🔐 Credenciales de admin:"
echo "   - Email:    admin@tuki.cl"
echo "   - Password: TukiAdmin2025!"
echo ""
echo "📋 Comandos útiles:"
echo "   - Ver logs:     docker-compose logs -f"
echo "   - Reiniciar:    docker-compose restart"
echo "   - Detener:      docker-compose down"
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
