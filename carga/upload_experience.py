#!/usr/bin/env python3
"""
⬆️ Upload Experience Script

Sube una experiencia al backend usando el JSON generado.
Robusto con validación, reintentos y manejo de errores enterprise.

Uso:
    export TUKI_API_URL=https://tuki.cl/api/v1
    export TUKI_SUPERADMIN_TOKEN=<jwt_token>
    python scripts/upload_experience.py carga/tours/santiago-historico/payload.json

O con credenciales:
    export TUKI_EMAIL=admin@tuki.cl
    export TUKI_PASSWORD=password
    python scripts/upload_experience.py payload.json

Output: ID de experiencia creada, instancias generadas, URL en frontend
"""

import os
import sys
import json
import time
import requests
from datetime import datetime
from pathlib import Path


# Configuración
API_URL = os.getenv('TUKI_API_URL', 'https://tuki.cl/api/v1')
TOKEN = os.getenv('TUKI_SUPERADMIN_TOKEN')
EMAIL = os.getenv('TUKI_EMAIL')
PASSWORD = os.getenv('TUKI_PASSWORD')
MAX_RETRIES = 3
RETRY_DELAY = 2  # segundos

# Colores para output
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
        log('❌ No TUKI_SUPERADMIN_TOKEN ni credenciales (TUKI_EMAIL, TUKI_PASSWORD) en env', RED)
        sys.exit(1)
    
    log(f'🔐 Obteniendo token con credenciales...', BLUE)
    
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


def validate_payload_locally(payload_file):
    """Valida payload localmente antes de enviar."""
    log('🔍 Validando payload localmente...', BLUE)
    
    # Buscar el script de validación en carga/ai_helpers/
    script_path = Path(__file__).parent / 'ai_helpers' / 'validate_payload.py'
    
    if not script_path.exists():
        log('⚠️ Script de validación no encontrado, saltando validación local', YELLOW)
        return True
    
    import subprocess
    
    result = subprocess.run(
        ['python', str(script_path), 'experience', payload_file],
        capture_output=True,
        text=True
    )
    
    try:
        validation_result = json.loads(result.stdout)
        
        if validation_result.get('valid'):
            log('✅ Payload válido localmente', GREEN)
            return True
        else:
            log('❌ Payload inválido:', RED)
            print(json.dumps(validation_result.get('errors', {}), indent=2))
            return False
    except json.JSONDecodeError:
        log(f'⚠️ No se pudo parsear resultado de validación', YELLOW)
        return True  # Continuar de todos modos


def upload_experience(payload, token, retry_count=0):
    """Sube experiencia al backend."""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    url = f'{API_URL}/superadmin/experiences/create-from-json/'
    
    try:
        log(f'📤 Enviando al backend: POST {url}', BLUE)
        
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
        
        if status_code == 400:
            # Error de validación
            log(f'❌ Error de validación (400):', RED)
            try:
                error_data = e.response.json()
                print(json.dumps(error_data, indent=2))
            except:
                print(e.response.text)
            return None
        
        elif status_code == 401:
            log(f'❌ No autorizado (401): Token inválido o expirado', RED)
            return None
        
        elif status_code == 403:
            log(f'❌ Prohibido (403): Usuario no es superadmin', RED)
            return None
        
        elif status_code >= 500:
            # Error del servidor, reintentar
            if retry_count < MAX_RETRIES:
                log(f'⚠️ Error del servidor ({status_code}), reintentando en {RETRY_DELAY}s... ({retry_count + 1}/{MAX_RETRIES})', YELLOW)
                time.sleep(RETRY_DELAY)
                return upload_experience(payload, token, retry_count + 1)
            else:
                log(f'❌ Error del servidor ({status_code}) después de {MAX_RETRIES} reintentos', RED)
                return None
        
        else:
            log(f'❌ Error HTTP {status_code}: {e}', RED)
            return None
    
    except requests.exceptions.Timeout:
        if retry_count < MAX_RETRIES:
            log(f'⚠️ Timeout, reintentando en {RETRY_DELAY}s... ({retry_count + 1}/{MAX_RETRIES})', YELLOW)
            time.sleep(RETRY_DELAY)
            return upload_experience(payload, token, retry_count + 1)
        else:
            log(f'❌ Timeout después de {MAX_RETRIES} reintentos', RED)
            return None
    
    except requests.exceptions.RequestException as e:
        log(f'❌ Error de conexión: {e}', RED)
        return None


def save_response(response, payload_file):
    """Guarda la respuesta del backend en un archivo."""
    response_file = payload_file.replace('.json', '_response.json')
    with open(response_file, 'w', encoding='utf-8') as f:
        json.dump(response, f, indent=2, ensure_ascii=False)
    log(f'💾 Respuesta guardada en: {response_file}', BLUE)


def get_frontend_url(experience_id, slug):
    """Genera URL del frontend para la experiencia."""
    frontend_url = API_URL.replace('/api/v1', '')
    return f'{frontend_url}/experiences/{slug or experience_id}'


def main():
    """Main function."""
    if len(sys.argv) < 2:
        log('❌ Uso: upload_experience.py <payload.json>', RED)
        log('   Variables de entorno:', BLUE)
        log('     TUKI_API_URL: URL base del API (default: https://tuki.cl/api/v1)', BLUE)
        log('     TUKI_SUPERADMIN_TOKEN: JWT token', BLUE)
        log('     O credenciales:', BLUE)
        log('     TUKI_EMAIL: Email del superadmin', BLUE)
        log('     TUKI_PASSWORD: Contraseña', BLUE)
        sys.exit(1)
    
    payload_file = sys.argv[1]
    
    # Verificar que el archivo existe
    if not os.path.exists(payload_file):
        log(f'❌ Archivo no encontrado: {payload_file}', RED)
        sys.exit(1)
    
    # Leer payload
    log(f'📄 Leyendo payload: {payload_file}', BLUE)
    try:
        with open(payload_file, 'r', encoding='utf-8') as f:
            payload_data = json.load(f)
    except json.JSONDecodeError as e:
        log(f'❌ JSON inválido: {e}', RED)
        sys.exit(1)
    
    # Validar estructura básica
    if 'organizer_id' not in payload_data:
        log('❌ Campo "organizer_id" requerido en el payload', RED)
        sys.exit(1)
    
    if 'experience_data' not in payload_data:
        log('❌ Campo "experience_data" requerido en el payload', RED)
        sys.exit(1)
    
    experience_data = payload_data['experience_data']
    
    log(f'📊 Experiencia: {experience_data.get("title", "Sin título")}', BLUE)
    log(f'🏢 Organizador: {payload_data["organizer_id"]}', BLUE)
    
    # Validar localmente
    if not validate_payload_locally(payload_file):
        log('❌ Abortando por errores de validación', RED)
        sys.exit(1)
    
    # Obtener token
    token = get_token()
    log('✅ Token obtenido', GREEN)
    
    # Subir experiencia
    log('=' * 60, BLUE)
    log('🚀 SUBIENDO EXPERIENCIA AL BACKEND', BLUE)
    log('=' * 60, BLUE)
    
    response = upload_experience(payload_data, token)
    
    if not response:
        log('=' * 60, RED)
        log('❌ FALLÓ LA SUBIDA', RED)
        log('=' * 60, RED)
        sys.exit(1)
    
    # Guardar respuesta
    save_response(response, payload_file)
    
    # Mostrar resultado
    log('=' * 60, GREEN)
    log('✅ EXPERIENCIA CREADA EXITOSAMENTE', GREEN)
    log('=' * 60, GREEN)
    
    log(f'🆔 ID: {response.get("id")}', GREEN)
    log(f'📝 Título: {response.get("title")}', GREEN)
    log(f'🔗 Slug: {response.get("slug")}', GREEN)
    log(f'📊 Estado: {response.get("status")}', GREEN)
    log(f'🗓️ Instancias creadas: {response.get("instances_created", 0)}', GREEN)
    
    if response.get('overrides_created', 0) > 0:
        log(f'💰 Price overrides creados: {response.get("overrides_created")}', GREEN)
    
    # URL del frontend
    frontend_url = get_frontend_url(response.get('id'), response.get('slug'))
    log(f'🌐 Ver en frontend: {frontend_url}', GREEN)
    
    log('=' * 60, GREEN)
    
    sys.exit(0)


if __name__ == '__main__':
    main()
