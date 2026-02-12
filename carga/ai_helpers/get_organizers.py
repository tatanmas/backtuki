#!/usr/bin/env python3
"""
🛠️ Get Organizers Helper

Lista organizadores disponibles en la base de datos con sus IDs, nombres, slugs
y módulos activos.

Uso:
    # Desde Docker (recomendado):
    docker exec backtuki-backend-1 python /app/carga/ai_helpers/get_organizers.py --active
    
    # Desde local:
    cd /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki
    python ../carga/ai_helpers/get_organizers.py --active

Output: JSON con organizadores
"""

import os
import sys
import json

# Detectar si estamos en Docker o local
if os.path.exists('/app/config'):
    # Estamos en Docker
    sys.path.insert(0, '/app')
    os.chdir('/app')
else:
    # Estamos en local
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.abspath(os.path.join(script_dir, '../../backtuki'))
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
import django
django.setup()

from apps.organizers.models import Organizer


def get_organizers(only_active=False, has_experiences=False):
    """Get list of organizers."""
    try:
        queryset = Organizer.objects.all()
        
        if only_active:
            # El campo correcto es 'status', no 'is_active'
            queryset = queryset.filter(status='active')
        
        if has_experiences:
            queryset = queryset.filter(has_experience_module=True)
        
        organizers = []
        for org in queryset.order_by('name'):
            organizers.append({
                'id': str(org.id),
                'name': org.name,
                'slug': org.slug,
                'status': org.status,
                'modules': {
                    'has_events_module': org.has_events_module,
                    'has_experience_module': org.has_experience_module,
                    'has_accommodation_module': org.has_accommodation_module
                },
                'is_student_center': org.is_student_center
            })
        
        return {
            'count': len(organizers),
            'organizers': organizers
        }
    
    except Exception as e:
        return {
            'error': True,
            'message': f'Error getting organizers: {str(e)}',
            'type': type(e).__name__
        }


def main():
    """Main function."""
    only_active = '--active' in sys.argv
    has_experiences = '--has-experiences' in sys.argv
    
    result = get_organizers(only_active=only_active, has_experiences=has_experiences)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    sys.exit(1 if result.get('error') else 0)


if __name__ == '__main__':
    main()
