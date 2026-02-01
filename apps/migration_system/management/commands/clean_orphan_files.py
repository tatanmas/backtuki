"""
🧹 COMANDO: Limpiar Referencias Huérfanas de Archivos Media

Este comando identifica y limpia referencias en la base de datos a archivos
media que no existen físicamente en el storage.

Uso:
    # Modo dry-run (solo mostrar)
    python manage.py clean_orphan_files
    
    # Eliminar referencias huérfanas
    python manage.py clean_orphan_files --delete
    
    # Con confirmación interactiva
    python manage.py clean_orphan_files --delete --interactive
"""

import os
from django.core.management.base import BaseCommand, CommandError
from django.apps import apps
from django.db import models
from django.core.files.storage import default_storage


class Command(BaseCommand):
    help = 'Limpia referencias huérfanas de archivos media que no existen físicamente'

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Eliminar las referencias huérfanas (sin este flag solo muestra)',
        )
        parser.add_argument(
            '--interactive',
            action='store_true',
            help='Pedir confirmación antes de cada eliminación',
        )
        parser.add_argument(
            '--app',
            type=str,
            help='Solo procesar modelos de esta app específica',
        )

    def handle(self, *args, **options):
        delete_mode = options['delete']
        interactive = options['interactive']
        target_app = options.get('app')
        
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('🧹 LIMPIEZA DE REFERENCIAS HUÉRFANAS DE ARCHIVOS MEDIA'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write('')
        
        if delete_mode:
            self.stdout.write(self.style.WARNING('⚠️  MODO: ELIMINACIÓN ACTIVA'))
        else:
            self.stdout.write(self.style.NOTICE('ℹ️  MODO: DRY-RUN (solo mostrar, no eliminar)'))
        self.stdout.write('')
        
        # Encontrar todos los campos de archivo
        file_fields = self.find_file_fields(target_app)
        
        self.stdout.write(f'📋 Encontrados {len(file_fields)} campos de archivo para revisar')
        self.stdout.write('')
        
        total_checked = 0
        total_orphans = 0
        total_deleted = 0
        
        for model, field_name in file_fields:
            model_name = f"{model._meta.app_label}.{model._meta.object_name}"
            self.stdout.write(f'🔍 Revisando {model_name}.{field_name}...')
            
            # Obtener objetos con archivos
            queryset = model.objects.exclude(**{f"{field_name}": ''}).exclude(**{f"{field_name}__isnull": True})
            count = queryset.count()
            
            if count == 0:
                self.stdout.write(self.style.NOTICE(f'   └─ Sin registros con archivos'))
                continue
            
            self.stdout.write(f'   ├─ {count} registros con archivos')
            
            orphans_in_model = 0
            deleted_in_model = 0
            
            for obj in queryset:
                total_checked += 1
                file_field = getattr(obj, field_name)
                
                if not file_field or not hasattr(file_field, 'name') or not file_field.name:
                    continue
                
                # Verificar si el archivo existe
                try:
                    exists = default_storage.exists(file_field.name)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'   ├─ Error verificando {file_field.name}: {e}'))
                    exists = False
                
                if not exists:
                    orphans_in_model += 1
                    total_orphans += 1
                    
                    self.stdout.write(self.style.WARNING(
                        f'   ├─ 🗑️  HUÉRFANO: {file_field.name}'
                    ))
                    self.stdout.write(self.style.WARNING(
                        f'   │    Objeto: {model_name} (id={obj.pk})'
                    ))
                    
                    if delete_mode:
                        should_delete = True
                        
                        if interactive:
                            response = input(f'   │    ¿Eliminar referencia? [y/N]: ')
                            should_delete = response.lower() in ['y', 'yes', 's', 'si', 'sí']
                        
                        if should_delete:
                            try:
                                # Limpiar el campo (setear a None o vacío)
                                setattr(obj, field_name, None)
                                obj.save(update_fields=[field_name])
                                deleted_in_model += 1
                                total_deleted += 1
                                self.stdout.write(self.style.SUCCESS(
                                    f'   │    ✅ Referencia eliminada'
                                ))
                            except Exception as e:
                                self.stdout.write(self.style.ERROR(
                                    f'   │    ❌ Error eliminando: {e}'
                                ))
                        else:
                            self.stdout.write(self.style.NOTICE(
                                f'   │    ⏭️  Omitido'
                            ))
            
            if orphans_in_model > 0:
                self.stdout.write(f'   └─ 📊 {orphans_in_model} huérfanos encontrados en este modelo')
                if delete_mode and deleted_in_model > 0:
                    self.stdout.write(self.style.SUCCESS(
                        f'      ✅ {deleted_in_model} referencias eliminadas'
                    ))
            else:
                self.stdout.write(self.style.SUCCESS(f'   └─ ✅ Sin huérfanos'))
            
            self.stdout.write('')
        
        # Resumen final
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('📊 RESUMEN'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(f'Total de archivos verificados:     {total_checked}')
        self.stdout.write(self.style.WARNING(f'Total de huérfanos encontrados:    {total_orphans}'))
        
        if delete_mode:
            self.stdout.write(self.style.SUCCESS(f'Total de referencias eliminadas:   {total_deleted}'))
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('✅ Limpieza completada'))
        else:
            self.stdout.write('')
            self.stdout.write(self.style.NOTICE('ℹ️  Para eliminar las referencias huérfanas, ejecuta:'))
            self.stdout.write(self.style.NOTICE('   python manage.py clean_orphan_files --delete'))
        
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write('')

    def find_file_fields(self, target_app=None):
        """
        Encuentra todos los campos FileField/ImageField en los modelos.
        
        Args:
            target_app: str, nombre de la app a filtrar (opcional)
            
        Returns:
            list: [(model, field_name), ...]
        """
        file_fields = []
        
        for model in apps.get_models():
            # Filtrar por app si se especificó
            if target_app and model._meta.app_label != target_app:
                continue
            
            for field in model._meta.get_fields():
                if isinstance(field, (models.FileField, models.ImageField)):
                    file_fields.append((model, field.name))
        
        return file_fields
