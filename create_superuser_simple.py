#!/usr/bin/env python
"""
Script para crear superusuario - Inspirado en AuroraDev
Adaptado para Tuki Platform (Django estándar, sin tenants)
"""

import os
import django

# Configurar Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.cloudrun")
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

# Variables de entorno (compatibles con las estándar de Django)
username = os.environ.get("DJANGO_SUPERUSER_USERNAME") or os.environ.get("DJANGO_SU_NAME")
email = os.environ.get("DJANGO_SUPERUSER_EMAIL") or os.environ.get("DJANGO_SU_EMAIL") 
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD") or os.environ.get("DJANGO_SU_PASSWORD")

if not username or not email or not password:
    print("⚠️  Variables de superusuario no definidas:")
    print("   - DJANGO_SUPERUSER_USERNAME (o DJANGO_SU_NAME)")
    print("   - DJANGO_SUPERUSER_EMAIL (o DJANGO_SU_EMAIL)")
    print("   - DJANGO_SUPERUSER_PASSWORD (o DJANGO_SU_PASSWORD)")
    print("   Saltando creación de superusuario...")
    exit(0)

# Verificar si el superusuario ya existe
if User.objects.filter(username=username).exists():
    print(f"✅ Superusuario '{username}' ya existe.")
elif User.objects.filter(email=email).exists():
    print(f"✅ Usuario con email '{email}' ya existe.")
else:
    print(f"👤 Creando superusuario '{username}'...")
    try:
        User.objects.create_superuser(
            username=username, 
            email=email, 
            password=password
        )
        print(f"✅ Superusuario '{username}' creado exitosamente!")
    except Exception as e:
        print(f"❌ Error creando superusuario: {e}")
        exit(1)
