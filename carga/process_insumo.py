#!/usr/bin/env python3
"""
🤖 Process Insumo Script

Toma una carpeta de insumos (texto, PDF, imágenes, JSON) y genera un payload.json
válido automáticamente para subir al backend.

Uso:
    python scripts/process_insumo.py \\
      --type tour \\
      --input carga/tours/santiago-historico/ \\
      --organizer 550e8400-e29b-41d4-a716-446655440000 \\
      --output carga/tours/santiago-historico/payload.json

Formatos soportados:
    - .txt, .md: Descripción, información general
    - .pdf: Itinerarios, guías (requiere pdfplumber o PyPDF2)
    - .jpg, .png, .webp: Imágenes (se suben a media o usan URLs)
    - .json: Datos parciales (se completan)

Variables de entorno opcionales:
    TUKI_API_URL: Para subir imágenes a media library
    TUKI_SUPERADMIN_TOKEN: Token para subir imágenes
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
import re


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


def slugify(text):
    """Convierte texto a slug URL-friendly."""
    text = text.lower()
    # Reemplazar caracteres especiales
    text = re.sub(r'[áàäâ]', 'a', text)
    text = re.sub(r'[éèëê]', 'e', text)
    text = re.sub(r'[íìïî]', 'i', text)
    text = re.sub(r'[óòöô]', 'o', text)
    text = re.sub(r'[úùüû]', 'u', text)
    text = re.sub(r'[ñ]', 'n', text)
    # Reemplazar espacios y caracteres no alfanuméricos
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')


def read_text_file(file_path):
    """Lee un archivo de texto."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        log(f'⚠️ Error leyendo {file_path}: {e}', YELLOW)
        return None


def extract_title_from_text(text):
    """Extrae título de un texto (primera línea o párrafo destacado)."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines:
        return None
    
    # Primera línea si es corta (menos de 100 chars)
    first_line = lines[0]
    if len(first_line) < 100:
        # Limpiar markdown headers
        first_line = first_line.lstrip('#').strip()
        return first_line
    
    return None


def extract_description_from_text(text, skip_first_line=False):
    """Extrae descripción de un texto."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    if skip_first_line and len(lines) > 1:
        lines = lines[1:]
    
    # Juntar líneas
    description = '\n\n'.join(lines)
    
    # Limpiar markdown headers extras
    description = re.sub(r'^#+\s+', '', description, flags=re.MULTILINE)
    
    return description.strip()


def parse_pdf(file_path):
    """Parsea un PDF para extraer texto e itinerario."""
    try:
        import pdfplumber
        
        log(f'📄 Parseando PDF: {file_path.name}', BLUE)
        
        with pdfplumber.open(file_path) as pdf:
            full_text = ''
            for page in pdf.pages:
                full_text += page.extract_text() + '\n\n'
        
        # Intentar extraer itinerario (buscar patrones como "10:00", "Paso 1", etc.)
        itinerary_items = extract_itinerary_from_text(full_text)
        
        return {
            'text': full_text.strip(),
            'itinerary': itinerary_items
        }
    
    except ImportError:
        log('⚠️ pdfplumber no instalado. Instala con: pip install pdfplumber', YELLOW)
        return None
    except Exception as e:
        log(f'⚠️ Error parseando PDF: {e}', YELLOW)
        return None


def extract_itinerary_from_text(text):
    """Extrae items de itinerario de un texto."""
    itinerary = []
    
    # Buscar líneas que parecen items de itinerario
    # Patrón: tiempo (HH:MM) seguido de título y descripción
    lines = text.split('\n')
    
    current_item = None
    time_pattern = re.compile(r'^(\d{1,2}:\d{2})')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Buscar tiempo al inicio de línea
        time_match = time_pattern.match(line)
        
        if time_match:
            # Nueva entrada de itinerario
            if current_item:
                itinerary.append(current_item)
            
            time_str = time_match.group(1)
            rest = line[len(time_str):].strip(' -:')
            
            current_item = {
                'time': time_str,
                'title': rest if len(rest) < 100 else rest[:97] + '...',
                'description': ''
            }
        elif current_item and line:
            # Agregar a descripción del item actual
            if current_item['description']:
                current_item['description'] += ' '
            current_item['description'] += line
    
    # Agregar último item
    if current_item:
        itinerary.append(current_item)
    
    return itinerary if itinerary else None


def find_images(input_dir):
    """Encuentra imágenes en la carpeta de input."""
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
    images = []
    
    for file_path in input_dir.rglob('*'):
        if file_path.suffix.lower() in image_extensions:
            images.append(file_path)
    
    # Ordenar por nombre
    images.sort(key=lambda p: p.name)
    
    return images


def load_media_ids(media_file):
    """Carga IDs y URLs de imágenes ya subidas desde media_ids.json."""
    try:
        with open(media_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extraer solo URLs (las que acepta el backend)
        urls = [asset['url'] for asset in data.get('assets', [])]
        
        log(f'✅ Cargadas {len(urls)} URLs de imágenes desde {Path(media_file).name}', GREEN)
        
        return urls
    
    except Exception as e:
        log(f'⚠️ Error cargando media_ids.json: {e}', YELLOW)
        return []


def process_input_directory(input_dir, organizer_id, entity_type='tour', media_file=None):
    """Procesa todos los archivos en el directorio de input."""
    input_path = Path(input_dir)
    
    if not input_path.exists():
        log(f'❌ Directorio no encontrado: {input_dir}', RED)
        return None
    
    log(f'📂 Procesando: {input_dir}', BLUE)
    
    # Inicializar estructura
    data = {
        'title': None,
        'description': None,
        'itinerary': None,
        'images': []
    }
    
    # 1. Buscar archivo JSON parcial (datos.json)
    json_file = input_path / 'datos.json'
    if json_file.exists():
        log(f'📋 Encontrado datos.json', BLUE)
        with open(json_file, 'r', encoding='utf-8') as f:
            partial_data = json.load(f)
            data.update(partial_data)
    
    # 2. Procesar archivos de texto
    for txt_file in list(input_path.glob('*.txt')) + list(input_path.glob('*.md')):
        log(f'📝 Procesando: {txt_file.name}', BLUE)
        text = read_text_file(txt_file)
        
        if text:
            # Extraer título si no lo tenemos
            if not data.get('title'):
                title = extract_title_from_text(text)
                if title:
                    data['title'] = title
                    log(f'  ✅ Título extraído: {title}', GREEN)
            
            # Extraer descripción
            if not data.get('description') or len(data['description']) < len(text):
                description = extract_description_from_text(
                    text,
                    skip_first_line=bool(data.get('title'))
                )
                data['description'] = description
                log(f'  ✅ Descripción extraída ({len(description)} chars)', GREEN)
    
    # 3. Procesar PDFs
    for pdf_file in input_path.glob('*.pdf'):
        pdf_data = parse_pdf(pdf_file)
        
        if pdf_data:
            # Usar texto del PDF si no tenemos descripción
            if not data.get('description') and pdf_data.get('text'):
                data['description'] = pdf_data['text'][:1000]  # Primeros 1000 chars
                log(f'  ✅ Descripción extraída del PDF', GREEN)
            
            # Usar itinerario del PDF
            if not data.get('itinerary') and pdf_data.get('itinerary'):
                data['itinerary'] = pdf_data['itinerary']
                log(f'  ✅ Itinerario extraído del PDF ({len(data["itinerary"])} items)', GREEN)
    
    # 4. Cargar imágenes desde media_ids.json (ya subidas)
    if media_file:
        media_path = Path(media_file)
        if media_path.exists():
            image_urls = load_media_ids(media_path)
            if image_urls:
                data['images'] = image_urls
        else:
            log(f'⚠️ Archivo media_ids.json no encontrado: {media_file}', YELLOW)
            log(f'   Ejecuta primero: python scripts/upload_media.py ...', YELLOW)
    else:
        # Buscar imágenes locales (advertir que hay que subirlas)
        images = find_images(input_path)
        if images:
            log(f'⚠️ {len(images)} imágenes encontradas en carpeta', YELLOW)
            log(f'   Debes subirlas primero con: python scripts/upload_media.py', YELLOW)
            log(f'   O especifica --media-file con las URLs ya subidas', YELLOW)
    
    # 5. Generar slug si no existe
    if not data.get('slug') and data.get('title'):
        data['slug'] = slugify(data['title'])
        log(f'  ✅ Slug generado: {data["slug"]}', GREEN)
    
    return data


def generate_payload(experience_data, organizer_id, entity_type='tour'):
    """Genera payload completo para el backend."""
    
    # Defaults para campos requeridos
    defaults = {
        'status': 'draft',
        'type': entity_type,
        'price': 0,
        'is_free_tour': True,
        'credit_per_person': 5000,
        'sales_cutoff_hours': 2,
        'min_participants': 1,
        'booking_horizon_days': 90
    }
    
    # Merge datos procesados con defaults
    final_data = {**defaults, **experience_data}
    
    # Estructura final del payload
    payload = {
        'organizer_id': organizer_id,
        'experience_data': final_data
    }
    
    return payload


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Procesa insumos y genera payload JSON para subir al backend'
    )
    parser.add_argument('--type', default='tour',
                       choices=['tour', 'activity', 'workshop', 'adventure'],
                       help='Tipo de experiencia')
    parser.add_argument('--input', required=True,
                       help='Carpeta con insumos')
    parser.add_argument('--organizer', required=True,
                       help='UUID del organizador')
    parser.add_argument('--media-file',
                       help='Archivo media_ids.json con imágenes ya subidas')
    parser.add_argument('--output', required=True,
                       help='Archivo de salida (payload.json)')
    
    args = parser.parse_args()
    
    log('=' * 60, BLUE)
    log('🤖 PROCESANDO INSUMOS', BLUE)
    log('=' * 60, BLUE)
    
    # Procesar directorio de input
    experience_data = process_input_directory(
        args.input,
        args.organizer,
        args.type,
        args.media_file
    )
    
    if not experience_data:
        log('❌ No se pudo procesar el directorio', RED)
        sys.exit(1)
    
    # Validar campos mínimos
    if not experience_data.get('title'):
        log('❌ No se pudo extraer título. Agrega un archivo de texto con el título.', RED)
        sys.exit(1)
    
    if not experience_data.get('description'):
        log('❌ No se pudo extraer descripción. Agrega un archivo de texto con la descripción.', RED)
        sys.exit(1)
    
    # Advertir si no hay imágenes
    if not experience_data.get('images'):
        log('⚠️ ADVERTENCIA: No se encontraron imágenes', YELLOW)
        log('   Sube las imágenes primero con: python scripts/upload_media.py', YELLOW)
        log('   Y especifica --media-file en este script', YELLOW)
    
    # Generar payload
    payload = generate_payload(experience_data, args.organizer, args.type)
    
    # Guardar payload
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    
    log('=' * 60, GREEN)
    log('✅ PAYLOAD GENERADO EXITOSAMENTE', GREEN)
    log('=' * 60, GREEN)
    log(f'📄 Archivo: {output_path}', GREEN)
    log(f'📝 Título: {experience_data.get("title")}', GREEN)
    log(f'📊 Descripción: {len(experience_data.get("description", ""))} caracteres', GREEN)
    
    if experience_data.get('itinerary'):
        log(f'🗓️ Itinerario: {len(experience_data["itinerary"])} items', GREEN)
    
    if experience_data.get('images'):
        log(f'📸 Imágenes: {len(experience_data["images"])} (URLs reales)', GREEN)
    else:
        log(f'⚠️ Imágenes: 0 (subir con upload_media.py)', YELLOW)
    
    log('=' * 60, GREEN)
    
    if not experience_data.get('images'):
        log('🚨 IMPORTANTE: Sube imágenes antes de crear la experiencia', YELLOW)
        log('   python scripts/upload_media.py carga/.../imagenes/*.jpg --organizer ... --output media_ids.json', YELLOW)
        log('   Luego re-ejecuta este script con --media-file media_ids.json', YELLOW)
    else:
        log(f'🚀 Siguiente paso: python scripts/upload_experience.py {output_path}', BLUE)
    
    sys.exit(0)


if __name__ == '__main__':
    main()
