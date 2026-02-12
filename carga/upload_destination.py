#!/usr/bin/env python3
"""
🗺️ Upload Destination Script

Sube o actualiza un destino (LandingDestination) en el backend.
Soporta crear destinos nuevos, actualizar existentes, y agregar guías de viaje.

Uso:
    export TUKI_API_URL=https://tuki.cl/api/v1
    export TUKI_SUPERADMIN_TOKEN=<jwt_token>
    
    # Crear nuevo destino
    python scripts/upload_destination.py --create payload.json
    
    # Actualizar destino existente
    python scripts/upload_destination.py --update <destination_id> payload.json
    
    # Agregar guías a destino existente
    python scripts/upload_destination.py --add-guides <destination_id> guias.json

Output: ID del destino, URL en frontend
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime
from pathlib import Path


# Configuración
API_URL = os.getenv('TUKI_API_URL', 'https://tuki.cl/api/v1')
TOKEN = os.getenv('TUKI_SUPERADMIN_TOKEN')
EMAIL = os.getenv('TUKI_EMAIL')
PASSWORD = os.getenv('TUKI_PASSWORD')

# Colores
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def log(message, color=''):
    """Log con timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{color}[{timestamp}] {message}{RESET}")


def get_token():
    """Obtiene token JWT con credenciales si no está en env."""
    if TOKEN:
        return TOKEN
    
    if not EMAIL or not PASSWORD:
        log('❌ No TUKI_SUPERADMIN_TOKEN ni credenciales en env', RED)
        sys.exit(1)
    
    log(f'🔐 Obteniendo token...', BLUE)
    
    try:
        response = requests.post(
            f'{API_URL}/auth/token/',
            json={'email': EMAIL, 'password': PASSWORD},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data['access']
    except requests.exceptions.RequestException as e:
        log(f'❌ Error obteniendo token: {e}', RED)
        sys.exit(1)


def create_destination(payload, token):
    """Crea un nuevo destino."""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    url = f'{API_URL}/superadmin/destinations/'
    
    try:
        log(f'📤 Creando destino: POST {url}', BLUE)
        
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=60
        )
        
        response.raise_for_status()
        return response.json()
    
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        log(f'❌ Error HTTP {status_code}', RED)
        
        try:
            error_data = e.response.json()
            print(json.dumps(error_data, indent=2))
        except:
            print(e.response.text)
        
        return None
    
    except requests.exceptions.RequestException as e:
        log(f'❌ Error de conexión: {e}', RED)
        return None


def update_destination(destination_id, payload, token):
    """Actualiza un destino existente."""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    url = f'{API_URL}/superadmin/destinations/{destination_id}/'
    
    try:
        log(f'📤 Actualizando destino: PATCH {url}', BLUE)
        
        response = requests.patch(
            url,
            json=payload,
            headers=headers,
            timeout=60
        )
        
        response.raise_for_status()
        return response.json()
    
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        log(f'❌ Error HTTP {status_code}', RED)
        
        try:
            error_data = e.response.json()
            print(json.dumps(error_data, indent=2))
        except:
            print(e.response.text)
        
        return None
    
    except requests.exceptions.RequestException as e:
        log(f'❌ Error de conexión: {e}', RED)
        return None


def get_destination(destination_id, token):
    """Obtiene un destino existente."""
    headers = {
        'Authorization': f'Bearer {token}'
    }
    
    url = f'{API_URL}/superadmin/destinations/{destination_id}/'
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    
    except requests.exceptions.RequestException as e:
        log(f'❌ Error obteniendo destino: {e}', RED)
        return None


def add_guides_to_destination(destination_id, guides, token):
    """Agrega guías de viaje a un destino existente."""
    # Primero obtenemos el destino
    destination = get_destination(destination_id, token)
    
    if not destination:
        return None
    
    # Obtenemos las guías existentes
    existing_guides = destination.get('travel_guides', [])
    
    # Agregamos las nuevas guías
    updated_guides = existing_guides + guides
    
    # Actualizamos el destino
    payload = {
        'travel_guides': updated_guides
    }
    
    log(f'📚 Agregando {len(guides)} guías al destino (total: {len(updated_guides)})', BLUE)
    
    return update_destination(destination_id, payload, token)


def get_frontend_url(destination_id, slug):
    """Genera URL del frontend para el destino."""
    frontend_url = API_URL.replace('/api/v1', '')
    return f'{frontend_url}/destinations/{slug or destination_id}'


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Sube o actualiza destinos en el backend'
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--create', action='store_true',
                      help='Crear nuevo destino')
    group.add_argument('--update', metavar='DESTINATION_ID',
                      help='Actualizar destino existente')
    group.add_argument('--add-guides', metavar='DESTINATION_ID',
                      help='Agregar guías a destino existente')
    
    parser.add_argument('payload_file',
                       help='Archivo JSON con datos del destino o guías')
    
    args = parser.parse_args()
    
    # Verificar archivo
    if not os.path.exists(args.payload_file):
        log(f'❌ Archivo no encontrado: {args.payload_file}', RED)
        sys.exit(1)
    
    # Leer payload
    log(f'📄 Leyendo: {args.payload_file}', BLUE)
    try:
        with open(args.payload_file, 'r', encoding='utf-8') as f:
            payload = json.load(f)
    except json.JSONDecodeError as e:
        log(f'❌ JSON inválido: {e}', RED)
        sys.exit(1)
    
    # Obtener token
    token = get_token()
    log('✅ Token obtenido', GREEN)
    
    # Ejecutar operación
    log('=' * 60, BLUE)
    
    if args.create:
        log('🌍 CREANDO DESTINO', BLUE)
        log('=' * 60, BLUE)
        
        log(f'📝 Nombre: {payload.get("name", "Sin nombre")}', BLUE)
        log(f'🏳️ País: {payload.get("country", "Sin país")}', BLUE)
        
        result = create_destination(payload, token)
    
    elif args.update:
        log(f'🌍 ACTUALIZANDO DESTINO: {args.update}', BLUE)
        log('=' * 60, BLUE)
        
        result = update_destination(args.update, payload, token)
    
    elif args.add_guides:
        log(f'📚 AGREGANDO GUÍAS A DESTINO: {args.add_guides}', BLUE)
        log('=' * 60, BLUE)
        
        # El payload debe ser un array de guías o un objeto con "guides"
        if isinstance(payload, list):
            guides = payload
        elif isinstance(payload, dict) and 'guides' in payload:
            guides = payload['guides']
        else:
            log('❌ Formato de guías inválido. Debe ser array o {guides: [...]}', RED)
            sys.exit(1)
        
        result = add_guides_to_destination(args.add_guides, guides, token)
    
    if not result:
        log('=' * 60, RED)
        log('❌ OPERACIÓN FALLÓ', RED)
        log('=' * 60, RED)
        sys.exit(1)
    
    # Mostrar resultado
    log('=' * 60, GREEN)
    log('✅ OPERACIÓN EXITOSA', GREEN)
    log('=' * 60, GREEN)
    
    log(f'🆔 ID: {result.get("id")}', GREEN)
    log(f'📝 Nombre: {result.get("name")}', GREEN)
    log(f'🔗 Slug: {result.get("slug")}', GREEN)
    log(f'🏳️ País: {result.get("country")}', GREEN)
    
    if result.get('travel_guides'):
        log(f'📚 Guías de viaje: {len(result["travel_guides"])}', GREEN)
    
    # URL del frontend
    frontend_url = get_frontend_url(result.get('id'), result.get('slug'))
    log(f'🌐 Ver en frontend: {frontend_url}', GREEN)
    
    log('=' * 60, GREEN)
    
    sys.exit(0)


if __name__ == '__main__':
    main()
