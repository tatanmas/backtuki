#!/usr/bin/env python3
"""
🛠️ Inspect Destination Helper

Obtiene la estructura completa de un destino existente (LandingDestination)
para usarlo como plantilla o referencia.

Uso:
    cd /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki
    python ../scripts/ai_helpers/inspect_destination.py valparaiso

Output: JSON con datos del destino
"""

import os
import sys
import django
import json

# Setup Django
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backtuki'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.landing_destinations.models import LandingDestination
from apps.landing_destinations.serializers import LandingDestinationSerializer


def inspect_destination(slug):
    """Inspect a destination by slug."""
    try:
        destination = LandingDestination.objects.get(slug=slug)
        serializer = LandingDestinationSerializer(destination)
        return serializer.data
    
    except LandingDestination.DoesNotExist:
        # List available destinations
        available = LandingDestination.objects.values_list('slug', flat=True)
        return {
            'error': True,
            'message': f'Destination not found: {slug}',
            'available_destinations': list(available)
        }
    
    except Exception as e:
        return {
            'error': True,
            'message': f'Error inspecting destination: {str(e)}',
            'type': type(e).__name__
        }


def main():
    """Main function."""
    if len(sys.argv) < 2:
        print(json.dumps({
            'error': True,
            'message': 'Usage: inspect_destination.py <slug>',
            'example': 'inspect_destination.py valparaiso'
        }, indent=2))
        sys.exit(1)
    
    slug = sys.argv[1]
    result = inspect_destination(slug)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    
    sys.exit(1 if isinstance(result, dict) and result.get('error') else 0)


if __name__ == '__main__':
    main()
