"""
Utilidades comunes para el sistema de migración.

Incluye introspección automática de modelos Django para generar
orden de importación basado en dependencias FK.
"""

import hashlib
import os
import logging
from collections import defaultdict
from django.apps import apps
from django.core.files.base import ContentFile
from django.db import connection

logger = logging.getLogger(__name__)


# Apps a excluir de la migración (sistema Django, admin, etc.)
EXCLUDED_APPS = {
    'admin', 'auth', 'contenttypes', 'sessions', 'django',
    'migration_system', 'otp', 'sync_woocommerce', 'validation'
}


def build_dependency_graph():
    """
    Construye grafo de dependencias FK entre modelos usando introspección.
    
    Analiza TODOS los modelos Django y extrae sus relaciones ForeignKey
    y OneToOneField para construir un grafo de dependencias.
    
    Returns:
        tuple: (graph, nullable_fks, all_models)
            - graph: dict {model_path: set(dependency_paths)}
            - nullable_fks: dict {(from_model, to_model): field_name}
            - all_models: set de todos los model_paths encontrados
    """
    graph = defaultdict(set)
    nullable_fks = {}
    all_models = set()
    
    for model in apps.get_models():
        app_label = model._meta.app_label
        
        # Excluir apps de sistema
        if app_label in EXCLUDED_APPS:
            continue
        
        model_path = f"{app_label}.{model.__name__}"
        all_models.add(model_path)
        
        # Asegurar que el modelo está en el grafo aunque no tenga dependencias
        if model_path not in graph:
            graph[model_path] = set()
        
        # Analizar campos para encontrar FKs
        for field in model._meta.get_fields():
            # Solo procesar ForeignKey y OneToOneField (no M2M ni reverse relations)
            if not hasattr(field, 'related_model') or not field.related_model:
                continue
            
            # Verificar que es una relación forward (many_to_one o one_to_one)
            if not (field.many_to_one or field.one_to_one):
                continue
            
            # Obtener modelo relacionado
            rel_model = field.related_model
            rel_app = rel_model._meta.app_label
            
            # Excluir relaciones a apps de sistema
            if rel_app in EXCLUDED_APPS:
                continue
            
            rel_path = f"{rel_app}.{rel_model.__name__}"
            
            # Agregar dependencia: model_path depende de rel_path
            graph[model_path].add(rel_path)
            
            # Registrar si el FK es nullable (para manejar ciclos)
            if getattr(field, 'null', False):
                nullable_fks[(model_path, rel_path)] = field.name
    
    logger.debug(f"Grafo de dependencias construido: {len(all_models)} modelos, {sum(len(deps) for deps in graph.values())} relaciones FK")
    
    return dict(graph), nullable_fks, all_models


def topological_sort_models(graph, all_models):
    """
    Ordena modelos topológicamente respetando dependencias FK.
    
    Implementa algoritmo de Kahn para ordenamiento topológico.
    Detecta y maneja ciclos usando FKs nullables.
    
    Args:
        graph: dict {model_path: set(dependency_paths)}
        all_models: set de todos los model_paths
        
    Returns:
        tuple: (sorted_order, circular_deps)
            - sorted_order: lista ordenada de model_paths
            - circular_deps: lista de tuplas (model_a, model_b, nullable_field)
    """
    # Calcular in-degree (cuántos modelos dependen de cada uno)
    in_degree = defaultdict(int)
    reverse_graph = defaultdict(set)  # {dependency: set(dependents)}
    
    for model_path in all_models:
        if model_path not in in_degree:
            in_degree[model_path] = 0
    
    for model_path, dependencies in graph.items():
        for dep in dependencies:
            if dep in all_models:  # Solo contar si el modelo existe
                in_degree[model_path] += 1
                reverse_graph[dep].add(model_path)
    
    # Cola de modelos sin dependencias (in_degree = 0)
    queue = [m for m in all_models if in_degree[m] == 0]
    sorted_order = []
    
    while queue:
        # Tomar modelo sin dependencias pendientes
        current = queue.pop(0)
        sorted_order.append(current)
        
        # Reducir in_degree de modelos que dependen de éste
        for dependent in reverse_graph[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)
    
    # Detectar ciclos: modelos que no fueron procesados
    remaining = [m for m in all_models if m not in sorted_order]
    circular_deps = []
    
    if remaining:
        logger.warning(f"Detectados {len(remaining)} modelos con dependencias circulares: {remaining[:5]}...")
        
        # Intentar resolver ciclos usando FKs nullables
        # Agregar modelos restantes en orden, rompiendo ciclos por FKs nullables
        for model in remaining:
            sorted_order.append(model)
            
            # Identificar qué dependencias son circulares
            for dep in graph.get(model, set()):
                if dep in remaining:
                    # Buscar si hay un FK nullable entre ellos
                    nullable_field = None
                    # Verificar en ambas direcciones
                    if (model, dep) in get_all_models_in_order_auto.nullable_fks_cache:
                        nullable_field = get_all_models_in_order_auto.nullable_fks_cache[(model, dep)]
                    circular_deps.append((model, dep, nullable_field))
    
    return sorted_order, circular_deps


def get_all_models_in_order_auto():
    """
    Genera orden de importación automáticamente usando introspección.
    
    Esta función reemplaza la lista manual MODEL_ORDER con un sistema
    dinámico que:
    1. Detecta TODOS los modelos Django del proyecto
    2. Analiza sus relaciones FK
    3. Genera orden topológico respetando dependencias
    4. Maneja ciclos usando FKs nullables
    
    Returns:
        tuple: (model_order, circular_deps, nullable_fks)
            - model_order: lista ordenada de model_paths para importación
            - circular_deps: dependencias circulares detectadas
            - nullable_fks: dict de FKs nullables para segunda pasada
    """
    # Construir grafo de dependencias
    graph, nullable_fks, all_models = build_dependency_graph()
    
    # Guardar en cache para uso en topological_sort
    get_all_models_in_order_auto.nullable_fks_cache = nullable_fks
    
    # Ordenar topológicamente
    sorted_order, circular_deps = topological_sort_models(graph, all_models)
    
    # Log del resultado
    logger.info(f"Orden de importación generado: {len(sorted_order)} modelos")
    if circular_deps:
        logger.warning(f"Dependencias circulares: {circular_deps}")
    
    return sorted_order, circular_deps, nullable_fks

# Cache para nullable_fks
get_all_models_in_order_auto.nullable_fks_cache = {}


def get_circular_fk_updates():
    """
    Identifica FKs circulares que requieren actualización en segunda pasada.
    
    Detecta pares de modelos con dependencias circulares donde uno de los FKs
    es nullable, permitiendo importar primero con FK=null y actualizar después.
    
    Returns:
        list: Lista de dicts con info de FKs a actualizar:
            [{
                'model': 'core.PlatformFlow',
                'field': 'primary_order',
                'target_model': 'events.Order',
                'target_field': 'id'
            }, ...]
    """
    # Conocidas dependencias circulares con FK nullable
    CIRCULAR_FK_UPDATES = [
        {
            'model': 'core.PlatformFlow',
            'field': 'primary_order',
            'target_model': 'events.Order',
            'target_field': 'id',
            'description': 'PlatformFlow.primary_order -> Order (circular con Order.flow)'
        },
    ]
    
    # Filtrar solo los que existen
    valid_updates = []
    for update in CIRCULAR_FK_UPDATES:
        try:
            app_label, model_name = update['model'].split('.')
            model = apps.get_model(app_label, model_name)
            
            # Verificar que el campo existe
            if hasattr(model, update['field']) or any(
                f.name == update['field'] for f in model._meta.get_fields()
            ):
                valid_updates.append(update)
        except (LookupError, ValueError):
            pass
    
    return valid_updates


def get_deferred_fk_fields():
    """
    Retorna lista de campos FK que deben ser importados con null inicialmente
    y actualizados en segunda pasada.
    
    Returns:
        dict: {model_path: [field_names]}
    """
    # FKs que causan ciclos y son nullables
    return {
        'core.PlatformFlow': ['primary_order'],  # Circular con Order.flow
    }


def get_all_models_in_order():
    """
    Retorna todos los modelos de la aplicación en orden de dependencias.
    
    USA ORDEN MANUAL VERIFICADO para garantizar integridad de datos.
    El orden ha sido validado para respetar todas las dependencias FK.
    
    Returns:
        list: Lista ordenada de model_paths (ej: ['users.User', 'events.Event', ...])
    """
    # NOTA: Introspección automática deshabilitada temporalmente porque
    # detecta falsos positivos de dependencias circulares.
    # El orden manual ha sido verificado y es correcto.
    
    # FALLBACK: Orden manual corregido con todas las dependencias
    MODEL_ORDER = [
        # === NIVEL 0: Sin dependencias FK ===
        'users.User',
        'core.Country',
        'events.Location',
        'events.EventCategory',
        
        # === NIVEL 1: Dependen de User o sin FK ===
        'organizers.Organizer',
        
        # === NIVEL 2: Dependen de Organizer/User ===
        'organizers.OrganizerOnboarding',
        'organizers.BillingDetails',
        'organizers.BankingDetails',
        'organizers.OrganizerUser',
        'organizers.OrganizerSubscription',
        'organizers.StudentCenterConfig',
        
        # Forms - ANTES de TicketTier (FK dependency)
        'forms.Form',
        'forms.FormField',
        'forms.FieldOption',
        'forms.FieldValidation',
        'forms.ConditionalLogic',
        
        # Media - antes de eventos que los referencien
        'media.MediaAsset',
        'media.MediaUsage',
        
        # === NIVEL 3: Events base ===
        'events.Event',
        'events.EventImage',
        'events.EventView',
        'events.ConversionFunnel',
        'events.EventPerformanceMetrics',
        'events.TicketCategory',
        'events.Coupon',  # Antes de Order y TicketTier
        
        # === NIVEL 4: Experiences base (antes de PlatformFlow) ===
        'experiences.TourLanguage',
        'experiences.Experience',
        'experiences.TourInstance',
        'experiences.TimeSlot',
        'experiences.ExperienceResource',
        'experiences.ExperienceDatePriceOverride',
        
        # === NIVEL 5: Core PlatformFlow (ANTES de Order) ===
        # PlatformFlow depende de User, Organizer, Event, Experience
        # primary_order es nullable - se actualiza en segunda pasada
        'core.PlatformFlow',
        
        # === NIVEL 6: TicketTier (depende de Form) ===
        'events.TicketTier',
        
        # === NIVEL 7: ExperienceReservation (antes de Order) ===
        'experiences.ExperienceReservation',
        
        # === NIVEL 8: Order (depende de PlatformFlow, Coupon) ===
        'events.Order',
        
        # === NIVEL 9: Dependen de Order ===
        'events.OrderItem',
        'events.Ticket',
        'events.ComplimentaryTicketInvitation',
        'events.TicketHolderReservation',
        'events.TicketHold',
        'events.CouponHold',
        'events.EmailLog',
        
        # === NIVEL 10: Dependen de Ticket ===
        'events.TicketNote',
        'forms.FormResponse',
        'forms.FormResponseFile',
        
        # === NIVEL 11: Events adicionales ===
        'events.EventCommunication',
        'events.SimpleBooking',
        'events.TicketRequest',
        
        # === NIVEL 12: Experiences adicionales ===
        'experiences.TourBooking',
        'experiences.ExperienceResourceHold',
        'experiences.ExperienceCapacityHold',
        'experiences.OrganizerCredit',
        'experiences.StudentCenterTimelineItem',
        'experiences.StudentInterest',
        
        # === NIVEL 13: Core adicional ===
        'core.CeleryTaskLog',
        'core.PlatformFlowEvent',
        
        # === NIVEL 14: Satisfaction ===
        'satisfaction.SatisfactionSurvey',
        'satisfaction.SatisfactionQuestion',
        'satisfaction.SatisfactionQuestionOption',
        'satisfaction.SatisfactionSurveySubmission',
        'satisfaction.SatisfactionResponse',
        'satisfaction.SatisfactionAnswer',
        
        # === NIVEL 15: WhatsApp ===
        'whatsapp.TourOperator',
        'whatsapp.WhatsAppSession',
        'whatsapp.WhatsAppChat',
        'whatsapp.WhatsAppMessage',
        'whatsapp.ExperienceOperatorBinding',
        'whatsapp.ExperienceGroupBinding',
        'whatsapp.WhatsAppReservationRequest',
        'whatsapp.WhatsAppReservationCode',
        
        # === NIVEL 16: Terminal ===
        'terminal.TerminalCompany',
        'terminal.TerminalDestination',
        'terminal.TerminalRoute',
        'terminal.TerminalTrip',
        'terminal.TerminalSchedule',
        'terminal.TerminalBooking',
        'terminal.TerminalExcelUpload',
        'terminal.TerminalAdvertisingSpace',
        'terminal.TerminalAdvertisingInteraction',
        'terminal.TerminalDestinationExperienceConfig',
        
        # === NIVEL 17: Payments (si existen) ===
        'payments.Payment',
        'payments.PaymentMethod',
        'payment_processor.Payment',
    ]
    
    # Filtrar solo modelos que existen
    existing_models = []
    for model_path in MODEL_ORDER:
        try:
            app_label, model_name = model_path.split('.')
            model = apps.get_model(app_label, model_name)
            existing_models.append(model_path)
        except (LookupError, ValueError):
            # Modelo no existe, skip
            pass
    
    return existing_models


def find_all_file_fields():
    """
    Encuentra todos los ImageField y FileField en todos los modelos.
    
    Returns:
        List of tuples: [(Model, field_name), ...]
    """
    file_fields = []
    
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if hasattr(field, 'upload_to'):
                # Es un FileField o ImageField
                file_fields.append((model, field.name))
    
    return file_fields


def calculate_file_checksum(file_field, algorithm='md5'):
    """
    Calcula el checksum de un archivo.
    
    Args:
        file_field: FileField o ImageField
        algorithm: 'md5' o 'sha256'
        
    Returns:
        str: Checksum en formato hexadecimal, None si el archivo no existe
    """
    if not file_field:
        return None
    
    try:
        # Verificar si el archivo existe físicamente antes de intentar abrirlo
        from django.core.files.storage import default_storage
        if not default_storage.exists(file_field.name):
            return None
        
        if algorithm == 'md5':
            hasher = hashlib.md5()
        elif algorithm == 'sha256':
            hasher = hashlib.sha256()
        else:
            raise ValueError(f"Algoritmo no soportado: {algorithm}")
        
        # Leer archivo en chunks para no cargar todo en memoria
        file_field.open('rb')
        for chunk in file_field.chunks(chunk_size=8192):
            hasher.update(chunk)
        file_field.close()
        
        return hasher.hexdigest()
    except Exception as e:
        print(f"Error calculando checksum: {e}")
        return None


def calculate_file_checksum_from_path(file_path, algorithm='md5'):
    """
    Calcula el checksum de un archivo desde su path.
    
    Args:
        file_path: Path al archivo
        algorithm: 'md5' o 'sha256'
        
    Returns:
        str: Checksum en formato "algorithm:hash", None si el archivo no existe
    """
    if not os.path.exists(file_path):
        return None
    
    try:
        if algorithm == 'md5':
            hasher = hashlib.md5()
        elif algorithm == 'sha256':
            hasher = hashlib.sha256()
        else:
            raise ValueError(f"Algoritmo no soportado: {algorithm}")
        
        # Leer archivo en chunks para no cargar todo en memoria
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        
        return f"{algorithm}:{hasher.hexdigest()}"
    except Exception as e:
        print(f"Error calculando checksum desde path: {e}")
        return None


def get_database_version():
    """
    Obtiene la versión de la base de datos.
    
    Returns:
        str: Versión de PostgreSQL
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        # Extraer solo "PostgreSQL 14.x"
        if 'PostgreSQL' in version:
            parts = version.split(',')[0]
            return parts
        return version


def get_serializer_for_model(model):
    """
    Obtiene el serializer apropiado para un modelo.
    
    Intenta usar serializers existentes en api/v1/, si no existe
    usa un serializer genérico.
    
    Args:
        model: Django model class
        
    Returns:
        Serializer class
    """
    from rest_framework import serializers
    
    app_label = model._meta.app_label
    model_name = model._meta.object_name
    
    # Intentar importar serializer existente
    try:
        # Patrón común: api.v1.{app_label}.serializers.{ModelName}Serializer
        module_path = f"api.v1.{app_label}.serializers"
        module = __import__(module_path, fromlist=[f"{model_name}Serializer"])
        serializer_class = getattr(module, f"{model_name}Serializer", None)
        
        if serializer_class:
            return serializer_class
    except (ImportError, AttributeError):
        pass
    
    # Si no existe, crear serializer genérico
    class GenericModelSerializer(serializers.ModelSerializer):
        class Meta:
            model_class = model
            fields = '__all__'
    
    GenericModelSerializer.Meta.model = model
    return GenericModelSerializer


def format_file_size(size_bytes):
    """
    Formatea tamaño de archivo en formato legible.
    
    Args:
        size_bytes: Tamaño en bytes
        
    Returns:
        str: Tamaño formateado (ej: "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def sanitize_filename(filename):
    """
    Sanitiza nombre de archivo para evitar path traversal.
    
    Args:
        filename: Nombre de archivo
        
    Returns:
        str: Nombre sanitizado
    """
    # Remover path components
    filename = os.path.basename(filename)
    # Remover caracteres peligrosos
    dangerous_chars = ['..', '/', '\\', '\x00']
    for char in dangerous_chars:
        filename = filename.replace(char, '_')
    return filename
