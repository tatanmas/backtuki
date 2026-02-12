#!/usr/bin/env python3
"""
📸 Upload Media Script

Sube imágenes a la media library del backend y devuelve IDs/URLs para incluir
en payloads de experiencias o destinos.

Uso:
    export TUKI_API_URL=https://tuki.cl/api/v1
    export TUKI_SUPERADMIN_TOKEN=<jwt_token>
    
    python scripts/upload_media.py \\
      carga/tours/santiago-historico/imagenes/*.jpg \\
      --organizer 550e8400-e29b-41d4-a716-446655440000 \\
      --output carga/tours/santiago-historico/media_ids.json

Output: JSON con IDs y URLs de MediaAssets creados
"""

import os
import sys
import json
import argparse
import requests
from pathlib import Path
from datetime import datetime


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
    """Obtiene token JWT."""
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


def upload_image(file_path, organizer_id, token):
    """Sube una imagen a la media library."""
    headers = {
        'Authorization': f'Bearer {token}'
    }
    
    # Data del form
    data = {
        'scope': 'organizer',
        'organizer': organizer_id
    }
    
    # Archivo
    try:
        with open(file_path, 'rb') as f:
            files = {
                'file': (file_path.name, f, f'image/{file_path.suffix[1:]}')
            }
            
            url = f'{API_URL}/media/assets/'
            
            log(f'📤 Subiendo: {file_path.name}', BLUE)
            
            response = requests.post(
                url,
                headers=headers,
                data=data,
                files=files,
                timeout=120
            )
            
            response.raise_for_status()
            result = response.json()
            
            log(f'  ✅ Subida exitosa: {result["id"][:8]}... ({result["size_bytes"]} bytes)', GREEN)
            
            return result
    
    except requests.exceptions.HTTPError as e:
        log(f'  ❌ Error HTTP {e.response.status_code}', RED)
        try:
            error_data = e.response.json()
            print(f'  {json.dumps(error_data, indent=2)}')
        except:
            print(f'  {e.response.text}')
        return None
    
    except requests.exceptions.RequestException as e:
        log(f'  ❌ Error de conexión: {e}', RED)
        return None
    
    except Exception as e:
        log(f'  ❌ Error: {e}', RED)
        return None


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Sube imágenes a media library y devuelve IDs/URLs'
    )
    parser.add_argument('images', nargs='+',
                       help='Rutas a imágenes (soporta glob patterns)')
    parser.add_argument('--organizer', required=True,
                       help='UUID del organizador')
    parser.add_argument('--output', required=True,
                       help='Archivo JSON de salida con IDs y URLs')
    
    args = parser.parse_args()
    
    # Expandir rutas (glob)
    image_paths = []
    for pattern in args.images:
        path = Path(pattern)
        if path.exists() and path.is_file():
            image_paths.append(path)
        else:
            # Intentar glob
            parent = path.parent if path.parent.exists() else Path.cwd()
            matches = list(parent.glob(path.name))
            image_paths.extend(matches)
    
    if not image_paths:
        log('❌ No se encontraron imágenes', RED)
        sys.exit(1)
    
    # Filtrar solo imágenes
    valid_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
    image_paths = [p for p in image_paths if p.suffix.lower() in valid_extensions]
    
    if not image_paths:
        log('❌ No se encontraron archivos de imagen válidos', RED)
        sys.exit(1)
    
    log('=' * 60, BLUE)
    log(f'📸 SUBIENDO {len(image_paths)} IMÁGENES', BLUE)
    log('=' * 60, BLUE)
    
    # Obtener token
    token = get_token()
    log('✅ Token obtenido', GREEN)
    
    # Subir imágenes
    results = []
    successful = 0
    failed = 0
    
    for img_path in image_paths:
        result = upload_image(img_path, args.organizer, token)
        
        if result:
            results.append({
                'id': result['id'],
                'url': result['url'],
                'original_filename': result['original_filename'],
                'size_bytes': result['size_bytes'],
                'width': result.get('width'),
                'height': result.get('height')
            })
            successful += 1
        else:
            failed += 1
    
    # Guardar resultados
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    output_data = {
        'uploaded_at': datetime.now().isoformat(),
        'organizer_id': args.organizer,
        'total': len(image_paths),
        'successful': successful,
        'failed': failed,
        'assets': results
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    # Resumen
    log('=' * 60, GREEN)
    log('📊 RESUMEN DE UPLOAD', GREEN)
    log('=' * 60, GREEN)
    log(f'✅ Exitosas: {successful}', GREEN)
    if failed > 0:
        log(f'❌ Fallidas: {failed}', RED)
    log(f'💾 Resultados guardados en: {output_path}', BLUE)
    log('=' * 60, GREEN)
    
    # Mostrar IDs para usar en payload
    if results:
        log('🔑 IDs de MediaAssets (para usar en experience_data):', BLUE)
        ids_list = [r['id'] for r in results]
        print(json.dumps(ids_list, indent=2))
        
        log('', '')
        log('🔗 URLs de imágenes (alternativa):', BLUE)
        urls_list = [r['url'] for r in results]
        print(json.dumps(urls_list, indent=2))
    
    sys.exit(0 if failed == 0 else 1)


if __name__ == '__main__':
    main()
