#!/bin/bash

# 🚀 ENTERPRISE ENTRYPOINT SCRIPT - Inspirado en AuroraDev
# Tuki Platform - Optimizado para Google Cloud Run

echo "Entrando a entrypoint.sh..."
echo "📋 Django Settings: $DJANGO_SETTINGS_MODULE"
echo "🌐 Port: $PORT"

# Ejecutar migraciones (equivalente a migrate_schemas --shared en AuroraDev)
echo "Ejecutando migrate..."
python manage.py migrate --noinput || { echo "migrate falló"; exit 1; }

# Crear tabla de cache si es necesaria
echo "Configurando cache..."
python manage.py createcachetable --noinput 2>/dev/null || echo "Cache table ya existe"

# Recopilar archivos estáticos
echo "Recopilando archivos estáticos..."
python manage.py collectstatic --noinput --clear || { echo "collectstatic falló"; exit 1; }

# Crear superusuario si las variables están definidas
echo "Verificando superusuario..."
python manage.py create_initial_superuser 2>/dev/null || echo "Superusuario ya existe o variables no definidas"

# Iniciar servidor con Gunicorn (para producción) o runserver (para desarrollo)
if [ "$DEBUG" = "True" ]; then
    echo "Iniciando servidor Django en modo desarrollo..."
    exec python manage.py runserver 0.0.0.0:$PORT
else
    echo "Iniciando servidor Gunicorn en modo producción..."
    exec gunicorn \
        --bind :$PORT \
        --workers 4 \
        --threads 8 \
        --timeout 120 \
        --keep-alive 2 \
        --max-requests 1000 \
        --max-requests-jitter 100 \
        --preload \
        --access-logfile - \
        --error-logfile - \
        --log-level info \
        config.wsgi:application
fi
