#!/usr/bin/env python
"""
🚀 ENTERPRISE: Script para probar todos los templates de email de confirmación
Envía el mismo ticket con 5 diseños diferentes para comparar
"""

import os
import sys
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.events.tasks import send_ticket_confirmation_email
from apps.events.models import Order

def test_all_email_templates(order_id):
    """
    Envía el mismo ticket con todos los templates disponibles
    """
    templates = [
        ('minimal_professional', '1. Minimalista Profesional'),
        ('corporate_tables', '2. Corporativo con Tablas'), 
        ('modern_clean', '3. Moderno Clean'),
        ('ticket_style', '4. Ticket Style'),
        ('professional_platform', '5. Professional Platform (Shotgun/Dice.fm Style)')
    ]
    
    print(f"🚀 Probando todos los templates de email para orden: {order_id}")
    print("=" * 70)
    
    # Verificar que la orden existe
    try:
        order = Order.objects.get(id=order_id)
        print(f"📋 Orden encontrada: {order.order_number}")
        print(f"🎫 Evento: {order.event.title}")
        print(f"👤 Cliente: {order.user.email}")
        print("=" * 70)
    except Order.DoesNotExist:
        print(f"❌ Error: No se encontró la orden {order_id}")
        return
    
    results = []
    
    for template_version, template_name in templates:
        print(f"\n📧 Enviando template: {template_name}")
        print(f"   Versión: {template_version}")
        
        # Configurar el template temporalmente
        original_template = getattr(settings, 'EMAIL_TEMPLATE_VERSION', 'v1_minimal')
        settings.EMAIL_TEMPLATE_VERSION = template_version
        
        try:
            # Enviar email con este template
            result = send_ticket_confirmation_email(order_id)
            
            if result.get('status') == 'sent':
                print(f"   ✅ Enviado exitosamente")
                print(f"   📊 Emails enviados: {result.get('emails_sent', 0)}")
                results.append({
                    'template': template_name,
                    'version': template_version,
                    'status': 'success',
                    'emails_sent': result.get('emails_sent', 0)
                })
            else:
                print(f"   ❌ Error al enviar: {result.get('reason', 'Unknown')}")
                results.append({
                    'template': template_name,
                    'version': template_version,
                    'status': 'failed',
                    'error': result.get('reason', 'Unknown')
                })
                
        except Exception as e:
            print(f"   💥 Excepción: {str(e)}")
            results.append({
                'template': template_name,
                'version': template_version,
                'status': 'error',
                'error': str(e)
            })
        finally:
            # Restaurar template original
            settings.EMAIL_TEMPLATE_VERSION = original_template
    
    # Resumen final
    print("\n" + "=" * 70)
    print("📊 RESUMEN DE ENVÍOS")
    print("=" * 70)
    
    successful = 0
    failed = 0
    
    for result in results:
        status_icon = "✅" if result['status'] == 'success' else "❌"
        print(f"{status_icon} {result['template']} ({result['version']})")
        if result['status'] == 'success':
            successful += 1
            print(f"    📧 Emails enviados: {result.get('emails_sent', 0)}")
        else:
            failed += 1
            print(f"    ⚠️  Error: {result.get('error', 'Unknown')}")
    
    print(f"\n📈 Total exitosos: {successful}/{len(templates)}")
    print(f"📉 Total fallidos: {failed}/{len(templates)}")
    
    if successful > 0:
        print(f"\n🎉 ¡Revisa tu email! Deberías recibir {successful} correos con diferentes diseños")
        print("📋 Compara los diseños y elige tu favorito")
    
    print("=" * 70)

if __name__ == "__main__":
    # Usar la misma orden que hemos estado probando
    test_order_id = "411354ea-aac6-497a-accd-3a2a0201ec83"
    
    if len(sys.argv) > 1:
        test_order_id = sys.argv[1]
    
    test_all_email_templates(test_order_id)
