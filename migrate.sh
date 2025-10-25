#!/bin/bash

# 🚀 Script de Migraciones para Tuki Backend
# =========================================

set -e  # Detener si hay errores

echo "🔍 Verificando estado de los contenedores..."
echo ""

# Verificar si docker-compose está corriendo
if ! docker-compose -f docker-compose.local.yml ps | grep -q "Up"; then
    echo "❌ Error: Los contenedores no están corriendo."
    echo "   Ejecuta primero: docker-compose -f docker-compose.local.yml up -d"
    exit 1
fi

echo "✅ Contenedores activos"
echo ""

# Esperar a que la base de datos esté lista
echo "⏳ Esperando a que la base de datos esté lista..."
timeout=60
counter=0

while ! docker-compose -f docker-compose.local.yml exec -T db pg_isready -U tuki_user > /dev/null 2>&1; do
    counter=$((counter + 1))
    if [ $counter -gt $timeout ]; then
        echo "❌ Error: La base de datos no respondió en $timeout segundos"
        exit 1
    fi
    echo "   Esperando... ($counter/$timeout)"
    sleep 1
done

echo "✅ Base de datos lista"
echo ""

# Mostrar estado actual de migraciones
echo "📋 Estado actual de las migraciones:"
echo "======================================"
docker-compose -f docker-compose.local.yml exec -T backend python manage.py showmigrations
echo ""

# Crear nuevas migraciones si hay cambios en los modelos
echo "🔨 Creando migraciones para cambios detectados..."
echo "================================================="
docker-compose -f docker-compose.local.yml exec -T backend python manage.py makemigrations
echo ""

# Ejecutar migraciones
echo "🚀 Aplicando migraciones a la base de datos..."
echo "=============================================="
docker-compose -f docker-compose.local.yml exec -T backend python manage.py migrate
echo ""

# Mostrar estado final de migraciones
echo "📊 Estado final de las migraciones:"
echo "===================================="
docker-compose -f docker-compose.local.yml exec -T backend python manage.py showmigrations | grep "\[X\]" | wc -l | awk '{print "   ✅ "$1" migraciones aplicadas"}'
echo ""

# Reiniciar servicios de Celery para que reconozcan las nuevas tablas
echo "🔄 Reiniciando servicios de Celery..."
echo "======================================"
docker-compose -f docker-compose.local.yml restart celery-worker celery-beat
echo ""

# Verificar que los servicios estén corriendo
echo "✅ Verificando servicios..."
sleep 3
docker-compose -f docker-compose.local.yml ps celery-worker celery-beat
echo ""

echo "✨ ¡Migraciones completadas exitosamente!"
echo ""
echo "📝 Comandos útiles:"
echo "   - Ver logs del backend:       docker-compose -f docker-compose.local.yml logs -f backend"
echo "   - Ver logs de Celery Worker:  docker-compose -f docker-compose.local.yml logs -f celery-worker"
echo "   - Ver logs de Celery Beat:    docker-compose -f docker-compose.local.yml logs -f celery-beat"
echo "   - Ver todas las migraciones:  docker-compose -f docker-compose.local.yml exec backend python manage.py showmigrations"
echo ""

