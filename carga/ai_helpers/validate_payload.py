#!/usr/bin/env python3
"""
🛠️ Validate Payload Helper

Valida un JSON contra el serializer de Django antes de enviarlo al backend,
para detectar errores localmente y ahorrar llamadas HTTP fallidas.

Uso:
    # Desde Docker (recomendado):
    docker exec backtuki-backend-1 python /app/carga/ai_helpers/validate_payload.py experience /app/carga/tours/test-tour-santiago/payload.json
    
    # Desde local:
    cd /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki
    python ../carga/ai_helpers/validate_payload.py experience payload.json

Output: JSON con resultado de validación
"""

import os
import sys
import json

# Detectar si estamos en Docker o local
if os.path.exists('/app/config'):
    sys.path.insert(0, '/app')
    os.chdir('/app')
else:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.abspath(os.path.join(script_dir, '../../backtuki'))
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
import django
django.setup()

from rest_framework import serializers


def validate_experience_payload(payload):
    """Validate experience payload using JsonExperienceCreateSerializer."""
    from api.v1.superadmin.serializers import JsonExperienceCreateSerializer
    
    serializer = JsonExperienceCreateSerializer(data=payload)
    
    if serializer.is_valid():
        return {
            'valid': True,
            'message': 'Payload is valid',
            'warnings': []
        }
    else:
        return {
            'valid': False,
            'errors': serializer.errors
        }


def validate_destination_payload(payload):
    """Validate destination payload using LandingDestinationSerializer."""
    from apps.landing_destinations.serializers import LandingDestinationSerializer
    
    serializer = LandingDestinationSerializer(data=payload)
    
    if serializer.is_valid():
        return {
            'valid': True,
            'message': 'Payload is valid',
            'warnings': []
        }
    else:
        return {
            'valid': False,
            'errors': serializer.errors
        }


def validate_payload(entity_type, payload):
    """Validate payload for different entity types."""
    validators = {
        'experience': validate_experience_payload,
        'destination': validate_destination_payload,
    }
    
    validator = validators.get(entity_type.lower())
    if not validator:
        return {
            'error': True,
            'message': f'Unknown entity type: {entity_type}',
            'available_types': list(validators.keys())
        }
    
    try:
        return validator(payload)
    except Exception as e:
        return {
            'error': True,
            'message': f'Error validating payload: {str(e)}',
            'type': type(e).__name__
        }


def main():
    """Main function."""
    if len(sys.argv) < 3:
        print(json.dumps({
            'error': True,
            'message': 'Usage: validate_payload.py <entity_type> <json_file>',
            'example': 'validate_payload.py experience payload.json',
            'available_types': ['experience', 'destination']
        }, indent=2))
        sys.exit(1)
    
    entity_type = sys.argv[1]
    json_file = sys.argv[2]
    
    # Read JSON file
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            payload = json.load(f)
    except FileNotFoundError:
        print(json.dumps({
            'error': True,
            'message': f'File not found: {json_file}'
        }, indent=2))
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(json.dumps({
            'error': True,
            'message': f'Invalid JSON: {str(e)}'
        }, indent=2))
        sys.exit(1)
    
    # Validate
    result = validate_payload(entity_type, payload)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Exit code 0 si válido, 1 si inválido o error
    if result.get('error') or not result.get('valid'):
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
