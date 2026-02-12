#!/usr/bin/env python3
"""
🛠️ Extract Model Schema Helper

Extrae la estructura completa de un modelo Django (campos, tipos, validaciones, choices)
para que el agente IA sepa exactamente qué datos enviar.

Uso:
    # Desde Docker (recomendado):
    docker exec backtuki-backend-1 python /app/carga/ai_helpers/extract_model_schema.py Experience
    
    # Desde local:
    cd /Users/sebamasretamal/Desktop/cursor/tukifull/backtuki
    python ../carga/ai_helpers/extract_model_schema.py Experience

Output: JSON con campos del modelo
"""

import os
import sys
import json
from decimal import Decimal

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

from django.apps import apps
from django.db import models
from django.core import validators


def get_field_info(field):
    """Extract info from a Django model field."""
    info = {
        'type': field.get_internal_type(),
        'required': not field.blank and not field.null and field.default == models.NOT_PROVIDED,
    }
    
    # Basic properties
    if hasattr(field, 'max_length') and field.max_length:
        info['max_length'] = field.max_length
    
    if hasattr(field, 'max_digits') and field.max_digits:
        info['max_digits'] = field.max_digits
        info['decimal_places'] = field.decimal_places
    
    if field.null:
        info['null'] = True
    
    if field.blank:
        info['blank'] = True
    
    if field.primary_key:
        info['primary_key'] = True
    
    if not field.editable:
        info['editable'] = False
    
    if field.unique:
        info['unique'] = True
    
    if field.db_index:
        info['db_index'] = True
    
    # Default value
    if field.default != models.NOT_PROVIDED:
        default_val = field.default
        # Callable defaults
        if callable(default_val):
            if default_val == dict:
                info['default'] = 'dict'
            elif default_val == list:
                info['default'] = 'list'
            else:
                info['default'] = 'callable'
        elif isinstance(default_val, (str, int, float, bool)):
            info['default'] = default_val
        elif isinstance(default_val, Decimal):
            info['default'] = float(default_val)
        else:
            info['default'] = str(default_val)
    
    # Choices
    if hasattr(field, 'choices') and field.choices:
        info['choices'] = [choice[0] for choice in field.choices]
    
    # Validators
    if field.validators:
        validator_info = []
        for validator in field.validators:
            if isinstance(validator, validators.MinValueValidator):
                validator_info.append(f"MinValueValidator({validator.limit_value})")
            elif isinstance(validator, validators.MaxValueValidator):
                validator_info.append(f"MaxValueValidator({validator.limit_value})")
            elif isinstance(validator, validators.MinLengthValidator):
                validator_info.append(f"MinLengthValidator({validator.limit_value})")
            elif isinstance(validator, validators.MaxLengthValidator):
                validator_info.append(f"MaxLengthValidator({validator.limit_value})")
            else:
                validator_info.append(validator.__class__.__name__)
        if validator_info:
            info['validators'] = validator_info
    
    # Help text
    if field.help_text:
        info['help_text'] = str(field.help_text)
    
    # Related fields
    if isinstance(field, (models.ForeignKey, models.OneToOneField)):
        info['related_model'] = field.related_model.__name__
        info['on_delete'] = field.remote_field.on_delete.__name__
    
    if isinstance(field, models.ManyToManyField):
        info['related_model'] = field.related_model.__name__
    
    return info


def extract_model_schema(model_name):
    """Extract schema for a Django model."""
    try:
        # Try to find the model
        model = None
        for app_config in apps.get_app_configs():
            try:
                model = app_config.get_model(model_name)
                break
            except LookupError:
                continue
        
        if not model:
            return {
                'error': True,
                'message': f'Model not found: {model_name}',
                'suggestion': 'Check available models with: python manage.py shell -c "from django.apps import apps; print([m.__name__ for m in apps.get_models()])"'
            }
        
        # Extract fields
        fields_info = {}
        for field in model._meta.get_fields():
            # Skip reverse relations
            if field.auto_created and not field.concrete:
                continue
            
            fields_info[field.name] = get_field_info(field)
        
        return {
            'model': model.__name__,
            'app': model._meta.app_label,
            'table_name': model._meta.db_table,
            'verbose_name': str(model._meta.verbose_name),
            'verbose_name_plural': str(model._meta.verbose_name_plural),
            'fields': fields_info
        }
    
    except Exception as e:
        return {
            'error': True,
            'message': f'Error extracting schema: {str(e)}',
            'type': type(e).__name__
        }


def main():
    """Main function."""
    if len(sys.argv) < 2:
        print(json.dumps({
            'error': True,
            'message': 'Usage: extract_model_schema.py <ModelName>',
            'example': 'extract_model_schema.py Experience'
        }, indent=2))
        sys.exit(1)
    
    model_name = sys.argv[1]
    result = extract_model_schema(model_name)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Exit code 0 si no hay error, 1 si hay error
    sys.exit(1 if result.get('error') else 0)


if __name__ == '__main__':
    main()
