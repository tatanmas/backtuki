#!/usr/bin/env python
"""
Script para configurar un organizador con módulo de experiencias (Template Principal)
Uso: python manage.py shell < scripts/setup_free_tours_organizer.py
O ejecutar directamente: python manage.py shell
"""

from apps.organizers.models import Organizer, OrganizerUser
from django.contrib.auth import get_user_model

User = get_user_model()


def setup_free_tours_organizer(
    organizer_slug: str = None,
    user_email: str = None,
    organizer_name: str = "Free Tours Santiago",
    organizer_slug: str = "free-tours-santiago",
    contact_email: str = "contacto@freetours.cl"
):
    """
    Configura un organizador para usar el módulo de experiencias con template Principal.
    
    Args:
        organizer_slug: Slug del organizador existente (si existe)
        user_email: Email del usuario a vincular
        organizer_name: Nombre del organizador (si se crea nuevo)
        organizer_slug: Slug del organizador (si se crea nuevo)
        contact_email: Email de contacto del organizador
    """
    
    # 1. Obtener o crear organizador
    if organizer_slug:
        try:
            organizer = Organizer.objects.get(slug=organizer_slug)
            print(f"✅ Organizador encontrado: {organizer.name}")
        except Organizer.DoesNotExist:
            print(f"❌ No se encontró organizador con slug: {organizer_slug}")
            return
    else:
        # Crear nuevo organizador
        organizer, created = Organizer.objects.get_or_create(
            slug=organizer_slug,
            defaults={
                'name': organizer_name,
                'contact_email': contact_email,
                'status': 'active',
                'has_experience_module': True,
                'experience_dashboard_template': 'principal',
                'onboarding_completed': True,
                'email_validated': True,
                'is_temporary': False,
            }
        )
        if created:
            print(f"✅ Organizador creado: {organizer.name}")
        else:
            print(f"✅ Organizador ya existía: {organizer.name}")
    
    # 2. Actualizar campos necesarios
    organizer.has_experience_module = True
    organizer.experience_dashboard_template = 'principal'
    organizer.status = 'active'
    organizer.onboarding_completed = True
    organizer.email_validated = True
    organizer.is_temporary = False
    organizer.save()
    
    print(f"✅ Organizador configurado:")
    print(f"   - Nombre: {organizer.name}")
    print(f"   - Slug: {organizer.slug}")
    print(f"   - Módulo experiencias: {organizer.has_experience_module}")
    print(f"   - Template: {organizer.experience_dashboard_template}")
    print(f"   - Estado: {organizer.status}")
    
    # 3. Vincular usuario si se proporciona
    if user_email:
        try:
            user = User.objects.get(email=user_email)
            organizer_user, created = OrganizerUser.objects.get_or_create(
                organizer=organizer,
                user=user,
                defaults={
                    'role': 'admin',
                    'can_manage_events': True,
                    'can_manage_experiences': True,  # ⚠️ CRÍTICO
                    'can_manage_accommodations': False,
                }
            )
            
            # Actualizar permisos si ya existía
            if not created:
                organizer_user.can_manage_experiences = True
                organizer_user.save()
            
            if created:
                print(f"✅ Usuario vinculado: {user.email}")
            else:
                print(f"✅ Permisos de usuario actualizados: {user.email}")
            print(f"   - Puede gestionar experiencias: {organizer_user.can_manage_experiences}")
            
        except User.DoesNotExist:
            print(f"⚠️  Usuario no encontrado: {user_email}")
            print(f"   El organizador está configurado, pero no hay usuario vinculado.")
    
    print("\n🎉 Configuración completada!")
    print(f"\n📝 Para probar:")
    print(f"   1. Inicia sesión con el usuario: {user_email if user_email else 'N/A'}")
    print(f"   2. Deberías ver el dashboard Principal en: /organizer/experiences/dashboard")
    
    return organizer


# Ejemplo de uso:
if __name__ == "__main__":
    # Opción 1: Actualizar organizador existente
    # setup_free_tours_organizer(
    #     organizer_slug='mi-organizador-existente',
    #     user_email='usuario@ejemplo.com'
    # )
    
    # Opción 2: Crear nuevo organizador
    # setup_free_tours_organizer(
    #     user_email='usuario@ejemplo.com',
    #     organizer_name='Free Tours Valparaíso',
    #     organizer_slug='free-tours-valparaiso',
    #     contact_email='contacto@freetoursvalpo.cl'
    # )
    
    print("📖 Para usar este script:")
    print("   1. Ejecuta: docker exec -it backtuki-backend-1 python manage.py shell")
    print("   2. Copia y pega el contenido de este archivo")
    print("   3. Llama a la función: setup_free_tours_organizer(...)")

