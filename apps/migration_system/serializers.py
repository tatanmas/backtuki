"""
🚀 ENTERPRISE MIGRATION SERIALIZERS

Serializers optimizados para export/import que manejan:
- ForeignKeys como IDs planos (no nested)
- Many-to-Many relationships separados en metadata
- Compatibilidad con el sistema de migración
"""

from rest_framework import serializers
from django.db import models as django_models


class MigrationSerializer(serializers.ModelSerializer):
    """
    Serializer base optimizado para migración que exporta:
    - ForeignKeys como IDs planos (strings/ints) en vez de objetos nested
    - Many-to-Many fields separados en metadata _m2m_relations
    - Estructura plana compatible con import directo
    
    Uso:
        serializer = MigrationSerializer.for_model(MyModel)
        data = serializer(instances, many=True).data
    """
    
    def to_representation(self, instance):
        """
        Convierte instancia a diccionario plano para migración.
        
        - ForeignKeys se convierten a IDs (no nested objects)
        - ManyToMany se extraen a metadata separada
        - Todos los otros campos se serializan normalmente
        """
        data = {}
        m2m_data = {}
        
        # Obtener todos los campos del modelo
        for field in instance._meta.get_fields():
            field_name = field.name
            
            # Skip campos reverse que no son propios del modelo
            if field.auto_created and not field.concrete:
                continue
            
            # Skip campos que no tienen valor en la instancia
            if not hasattr(instance, field_name):
                continue
            
            try:
                value = getattr(instance, field_name)
                
                # Manejo de ManyToMany - extraer a metadata separada
                if field.many_to_many:
                    # Obtener lista de IDs
                    m2m_ids = []
                    if hasattr(value, 'all'):
                        m2m_ids = list(value.all().values_list('pk', flat=True))
                    m2m_data[field_name] = m2m_ids
                    # NO incluir en data principal
                    continue
                
                # Manejo de ForeignKey - convertir a ID plano
                elif isinstance(field, django_models.ForeignKey):
                    if value is not None:
                        # Extraer solo el ID
                        if hasattr(value, 'pk'):
                            data[field_name + '_id'] = str(value.pk)
                        else:
                            data[field_name + '_id'] = str(value)
                    else:
                        data[field_name + '_id'] = None
                    continue
                
                # Manejo de OneToOne - similar a ForeignKey
                elif isinstance(field, django_models.OneToOneField):
                    if value is not None:
                        if hasattr(value, 'pk'):
                            data[field_name + '_id'] = str(value.pk)
                        else:
                            data[field_name + '_id'] = str(value)
                    else:
                        data[field_name + '_id'] = None
                    continue
                
                # Campos normales - serializar directamente
                else:
                    # FileField/ImageField - solo guardar path
                    if hasattr(value, 'name') and hasattr(field, 'upload_to'):
                        data[field_name] = value.name if value else None
                    # UUID - convertir a string
                    elif hasattr(value, 'hex'):
                        data[field_name] = str(value)
                    # Datetime - ISO format
                    elif hasattr(value, 'isoformat'):
                        data[field_name] = value.isoformat()
                    # Decimal - convertir a float
                    elif hasattr(value, 'as_tuple'):
                        data[field_name] = float(value)
                    # Otros tipos - directo
                    else:
                        data[field_name] = value
                        
            except Exception as e:
                # Si hay error obteniendo el campo, skip silenciosamente
                # Esto evita que un campo problemático bloquee toda la serialización
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Error serializando campo {field_name}: {e}")
                continue
        
        # Agregar metadata de M2M si existen
        if m2m_data:
            data['_m2m_relations'] = m2m_data
        
        return data
    
    @classmethod
    def for_model(cls, model_class):
        """
        Crea un serializer para un modelo específico.
        
        Args:
            model_class: Django model class
            
        Returns:
            MigrationSerializer class configurada para el modelo
        """
        class DynamicMigrationSerializer(cls):
            class Meta:
                model = model_class
                fields = '__all__'
        
        return DynamicMigrationSerializer


def get_migration_serializer_for_model(model):
    """
    Obtiene un MigrationSerializer apropiado para un modelo.
    
    Esta función es un wrapper que siempre retorna un MigrationSerializer
    optimizado para migración, independientemente de si existe un serializer
    custom en api/v1/.
    
    Args:
        model: Django model class
        
    Returns:
        MigrationSerializer class
    """
    return MigrationSerializer.for_model(model)
