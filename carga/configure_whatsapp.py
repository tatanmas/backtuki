#!/usr/bin/env python3
"""
📱 Configure WhatsApp Script

Configura el operador turístico y grupo de WhatsApp para una experiencia
que use reservas por WhatsApp.

Uso:
    export TUKI_API_URL=https://tuki.cl/api/v1
    export TUKI_SUPERADMIN_TOKEN=<jwt_token>
    
    python scripts/configure_whatsapp.py \\
      --experience <experience_id> \\
      --operator-phone +56912345678 \\
      --operator-name "Juan Pérez" \\
      --group-id <whatsapp_group_id>

Nota: Requiere que la experiencia tenga is_whatsapp_reservation=true
"""

import os
import sys
import json
import argparse
import requests
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
    
    try:
        response = requests.post(
            f'{API_URL}/auth/token/',
            json={'email': EMAIL, 'password': PASSWORD},
            timeout=30
        )
        response.raise_for_status()
        return response.json()['access']
    except requests.exceptions.RequestException as e:
        log(f'❌ Error obteniendo token: {e}', RED)
        sys.exit(1)


def get_experience(experience_id, token):
    """Obtiene datos de la experiencia."""
    headers = {'Authorization': f'Bearer {token}'}
    
    try:
        response = requests.get(
            f'{API_URL}/experiences/experiences/{experience_id}/',
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        log(f'❌ Error obteniendo experiencia: {e}', RED)
        return None


def configure_whatsapp_operator(experience_id, operator_data, token):
    """Configura el operador de WhatsApp para la experiencia."""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    # El endpoint exacto depende de tu backend
    # Este es un ejemplo basado en los endpoints de WhatsApp que vi
    url = f'{API_URL}/superadmin/whatsapp/bind-experience-operator/'
    
    payload = {
        'experience_id': experience_id,
        **operator_data
    }
    
    try:
        log(f'📱 Configurando operador WhatsApp...', BLUE)
        
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=60
        )
        
        response.raise_for_status()
        result = response.json()
        
        log(f'  ✅ Operador configurado', GREEN)
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


def assign_whatsapp_group(experience_id, group_id, token):
    """Asigna un grupo de WhatsApp a la experiencia."""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    url = f'{API_URL}/superadmin/whatsapp/experiences/{experience_id}/group/'
    
    payload = {
        'group_id': group_id
    }
    
    try:
        log(f'👥 Asignando grupo de WhatsApp...', BLUE)
        
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=60
        )
        
        response.raise_for_status()
        result = response.json()
        
        log(f'  ✅ Grupo asignado', GREEN)
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


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Configura WhatsApp para una experiencia'
    )
    parser.add_argument('--experience', required=True,
                       help='UUID de la experiencia')
    parser.add_argument('--operator-phone', required=True,
                       help='Teléfono del operador (+56912345678)')
    parser.add_argument('--operator-name',
                       help='Nombre del operador')
    parser.add_argument('--group-id',
                       help='ID del grupo de WhatsApp')
    
    args = parser.parse_args()
    
    log('=' * 60, BLUE)
    log('📱 CONFIGURANDO WHATSAPP', BLUE)
    log('=' * 60, BLUE)
    
    # Obtener token
    token = get_token()
    log('✅ Token obtenido', GREEN)
    
    # Verificar que la experiencia existe y tiene is_whatsapp_reservation=true
    experience = get_experience(args.experience, token)
    
    if not experience:
        log('❌ No se pudo obtener la experiencia', RED)
        sys.exit(1)
    
    if not experience.get('is_whatsapp_reservation'):
        log('⚠️ ADVERTENCIA: La experiencia no tiene is_whatsapp_reservation=true', YELLOW)
        log('   Las reservas NO funcionarán por WhatsApp', YELLOW)
    
    log(f'📝 Experiencia: {experience.get("title")}', BLUE)
    
    # Configurar operador
    operator_data = {
        'operator_phone': args.operator_phone
    }
    
    if args.operator_name:
        operator_data['operator_name'] = args.operator_name
    
    operator_result = configure_whatsapp_operator(
        args.experience,
        operator_data,
        token
    )
    
    if not operator_result:
        log('❌ Falló configuración de operador', RED)
        sys.exit(1)
    
    # Asignar grupo si se proporcionó
    group_result = None
    if args.group_id:
        group_result = assign_whatsapp_group(
            args.experience,
            args.group_id,
            token
        )
        
        if not group_result:
            log('⚠️ Falló asignación de grupo (opcional)', YELLOW)
    
    # Resumen
    log('=' * 60, GREEN)
    log('✅ CONFIGURACIÓN COMPLETA', GREEN)
    log('=' * 60, GREEN)
    log(f'📱 Operador: {args.operator_phone}', GREEN)
    if args.operator_name:
        log(f'👤 Nombre: {args.operator_name}', GREEN)
    if args.group_id:
        log(f'👥 Grupo: {args.group_id}', GREEN)
    log('=' * 60, GREEN)
    
    sys.exit(0)


if __name__ == '__main__':
    main()
