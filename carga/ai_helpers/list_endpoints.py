#!/usr/bin/env python3
"""
🛠️ List Endpoints Helper

Lista todos los endpoints disponibles para una entidad (o todos si no se especifica),
con método HTTP, URL, autenticación requerida y descripción.

Uso:
    cd /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki
    python ../scripts/ai_helpers/list_endpoints.py experience

Output: JSON con endpoints
"""

import os
import sys
import django
import json

# Setup Django
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backtuki'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()


# Mapeo manual de endpoints conocidos (puede extenderse)
ENDPOINTS_MAP = {
    'experience': [
        {
            'method': 'POST',
            'url': '/api/v1/superadmin/experiences/create-from-json/',
            'auth': 'IsSuperUser (JWT)',
            'description': 'Create experience from JSON data',
            'body': {
                'organizer_id': 'UUID of organizer',
                'experience_data': 'JSON object with experience fields'
            }
        },
        {
            'method': 'GET',
            'url': '/api/v1/experiences/public/<slug_or_id>/',
            'auth': 'None (public)',
            'description': 'Get public experience details'
        },
        {
            'method': 'GET',
            'url': '/api/v1/experiences/public/',
            'auth': 'None (public)',
            'description': 'List public experiences',
            'query_params': ['status', 'type', 'search']
        },
        {
            'method': 'GET',
            'url': '/api/v1/experiences/experiences/',
            'auth': 'Organizer or SuperAdmin',
            'description': 'List experiences (filtered by permissions)'
        },
        {
            'method': 'POST',
            'url': '/api/v1/experiences/experiences/',
            'auth': 'Organizer',
            'description': 'Create experience (organizer is set from current user)'
        },
        {
            'method': 'GET',
            'url': '/api/v1/experiences/experiences/<id>/',
            'auth': 'Organizer (own) or SuperAdmin',
            'description': 'Get experience details'
        },
        {
            'method': 'PATCH',
            'url': '/api/v1/experiences/experiences/<id>/',
            'auth': 'Organizer (own) or SuperAdmin',
            'description': 'Update experience (partial)'
        },
        {
            'method': 'DELETE',
            'url': '/api/v1/experiences/experiences/<id>/',
            'auth': 'Organizer (own) or SuperAdmin',
            'description': 'Delete experience (soft delete)'
        },
        {
            'method': 'POST',
            'url': '/api/v1/experiences/experiences/<id>/images/from-assets/',
            'auth': 'Organizer (own) or SuperAdmin',
            'description': 'Link media assets to experience images',
            'body': {
                'asset_ids': 'List of MediaAsset UUIDs',
                'replace': 'Boolean (optional, default false)'
            }
        },
        {
            'method': 'GET',
            'url': '/api/v1/experiences/public/<experience_id>/instances/',
            'auth': 'None (public)',
            'description': 'List tour instances for an experience'
        },
        {
            'method': 'POST',
            'url': '/api/v1/experiences/public/<experience_id>/reserve/',
            'auth': 'Optional',
            'description': 'Create reservation for experience'
        }
    ],
    'destination': [
        {
            'method': 'GET',
            'url': '/api/v1/superadmin/destinations/',
            'auth': 'IsSuperUser',
            'description': 'List landing destinations'
        },
        {
            'method': 'POST',
            'url': '/api/v1/superadmin/destinations/',
            'auth': 'IsSuperUser',
            'description': 'Create landing destination'
        },
        {
            'method': 'GET',
            'url': '/api/v1/superadmin/destinations/<id>/',
            'auth': 'IsSuperUser',
            'description': 'Get destination details'
        },
        {
            'method': 'PATCH',
            'url': '/api/v1/superadmin/destinations/<id>/',
            'auth': 'IsSuperUser',
            'description': 'Update destination (partial)'
        },
        {
            'method': 'DELETE',
            'url': '/api/v1/superadmin/destinations/<id>/',
            'auth': 'IsSuperUser',
            'description': 'Delete destination'
        }
    ],
    'organizer': [
        {
            'method': 'GET',
            'url': '/api/v1/organizers/',
            'auth': 'Authenticated',
            'description': 'List organizers'
        },
        {
            'method': 'GET',
            'url': '/api/v1/organizers/<id>/',
            'auth': 'Authenticated',
            'description': 'Get organizer details'
        }
    ],
    'media': [
        {
            'method': 'POST',
            'url': '/api/v1/media/assets/',
            'auth': 'Organizer or SuperAdmin',
            'description': 'Upload media asset',
            'body': 'FormData with file'
        },
        {
            'method': 'GET',
            'url': '/api/v1/media/assets/',
            'auth': 'Organizer or SuperAdmin',
            'description': 'List media assets (filtered by scope/organizer)',
            'query_params': ['scope', 'organizer_id', 'show_deleted']
        },
        {
            'method': 'GET',
            'url': '/api/v1/media/assets/<id>/',
            'auth': 'Organizer or SuperAdmin',
            'description': 'Get media asset details'
        },
        {
            'method': 'DELETE',
            'url': '/api/v1/media/assets/<id>/',
            'auth': 'Organizer (own) or SuperAdmin',
            'description': 'Delete media asset (soft delete)'
        }
    ],
    'auth': [
        {
            'method': 'POST',
            'url': '/api/v1/auth/token/',
            'auth': 'None',
            'description': 'Obtain JWT token',
            'body': {
                'email': 'user@example.com',
                'password': 'password'
            }
        },
        {
            'method': 'POST',
            'url': '/api/v1/auth/token/refresh/',
            'auth': 'None',
            'description': 'Refresh JWT token',
            'body': {
                'refresh': 'refresh_token'
            }
        }
    ]
}


def list_endpoints(entity=None):
    """List endpoints for an entity or all."""
    if entity:
        entity_lower = entity.lower()
        if entity_lower not in ENDPOINTS_MAP:
            return {
                'error': True,
                'message': f'Unknown entity: {entity}',
                'available_entities': list(ENDPOINTS_MAP.keys())
            }
        return {
            'entity': entity_lower,
            'endpoints': ENDPOINTS_MAP[entity_lower]
        }
    else:
        # Return all endpoints grouped by entity
        return {
            'all_endpoints': ENDPOINTS_MAP
        }


def main():
    """Main function."""
    entity = sys.argv[1] if len(sys.argv) > 1 else None
    result = list_endpoints(entity)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    sys.exit(1 if result.get('error') else 0)


if __name__ == '__main__':
    main()
