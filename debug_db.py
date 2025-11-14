#!/usr/bin/env python
"""
Script de diagnóstico para verificar la conexión a la base de datos
"""
import os
import django
from django.conf import settings

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.cloudrun')
django.setup()

from django.db import connection
from django.core.management.color import no_style

def main():
    print("🔍 DIAGNÓSTICO DE BASE DE DATOS")
    print("=" * 50)
    
    # Mostrar configuración actual
    db_config = settings.DATABASES['default']
    print(f"📊 ENGINE: {db_config['ENGINE']}")
    print(f"📊 NAME: {db_config['NAME']}")
    print(f"📊 USER: {db_config['USER']}")
    print(f"📊 HOST: {db_config['HOST']}")
    print(f"📊 PORT: {db_config['PORT']}")
    
    # Probar conexión
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            print(f"✅ CONEXIÓN EXITOSA: {version}")
            
            # Contar eventos
            cursor.execute("SELECT COUNT(*) FROM events_event;")
            event_count = cursor.fetchone()[0]
            print(f"📊 EVENTOS EN DB: {event_count}")
            
            # Mostrar algunas tablas
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' LIMIT 5;")
            tables = cursor.fetchall()
            print(f"📊 PRIMERAS 5 TABLAS: {[t[0] for t in tables]}")
            
    except Exception as e:
        print(f"❌ ERROR DE CONEXIÓN: {e}")
        print(f"❌ TIPO DE ERROR: {type(e).__name__}")

if __name__ == "__main__":
    main()
