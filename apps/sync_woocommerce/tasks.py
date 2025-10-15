"""
Tareas asíncronas de Celery para sincronización WooCommerce

Estas tareas manejan la sincronización de eventos de forma asíncrona
sin afectar el rendimiento del sistema principal.
"""

import logging
import traceback
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.core.mail import mail_admins

from .models import SyncConfiguration, SyncExecution
from .sync_engine.integration import (
    EventMigrationRequest,
    IntegrationConfig,
    EventMigrator
)
from .sync_engine.ssh_mysql_handler import SSHMySQLHandler
from .sync_engine.woo_models import EventSyncData
from .sync_engine.django_config import get_sync_config

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def sync_woocommerce_event(self, sync_config_id: str, trigger: str = 'scheduled', user_id: int = None):
    """
    Tarea principal de sincronización de un evento desde WooCommerce
    
    Args:
        sync_config_id: ID de la configuración de sincronización
        trigger: Tipo de disparador ('scheduled', 'manual', 'api')
        user_id: ID del usuario que disparó la sincronización (opcional)
    """
    
    execution = None
    
    try:
        # Obtener configuración
        sync_config = SyncConfiguration.objects.get(id=sync_config_id)
        
        # Crear registro de ejecución
        execution = SyncExecution.objects.create(
            configuration=sync_config,
            status='running',
            trigger=trigger,
            celery_task_id=self.request.id,
            triggered_by_id=user_id
        )
        
        logger.info(f"Iniciando sincronización: {sync_config.name} (ID: {sync_config_id})")
        
        # Configurar integración
        integration_config = IntegrationConfig(
            backend_url=f"http://localhost:8000",  # URL local del backend
            api_token="",  # Se manejará internamente
            default_service_fee_percentage=sync_config.service_fee_percentage
        )
        
        # Configurar migración
        migration_request = EventMigrationRequest(
            event_name=sync_config.event_name,
            organizer_email=sync_config.organizer_email,
            organizer_name=sync_config.organizer_name,
            service_fee_percentage=sync_config.service_fee_percentage,
            event_description=sync_config.event_description,
            event_start_date=sync_config.event_start_date.isoformat() if sync_config.event_start_date else None,
            event_end_date=sync_config.event_end_date.isoformat() if sync_config.event_end_date else None
        )
        
        # Extraer datos de WooCommerce
        logger.info(f"Extrayendo datos de WooCommerce para producto {sync_config.woocommerce_product_id}")
        woo_data = extract_woocommerce_data(sync_config.woocommerce_product_id)
        
        # Migrar al backend Django
        logger.info("Migrando datos al backend Django")
        migrator = EventMigrator(integration_config)
        result = migrator.migrate_event(woo_data, migration_request)
        
        if result['success']:
            # Actualizar configuración con referencias
            # Actualizar configuración con resultados (convertir strings a UUIDs de forma robusta)
            import uuid
            
            def safe_uuid_convert(uuid_string, field_name):
                """Convierte string a UUID de forma segura"""
                try:
                    if not uuid_string:
                        return None
                    
                    # Si es un número simple (como "5"), no es un UUID válido
                    if isinstance(uuid_string, str) and uuid_string.isdigit():
                        logger.warning(f"Error convirtiendo UUID para {field_name}: {uuid_string} - badly formed hexadecimal UUID string")
                        return None
                    
                    if isinstance(uuid_string, str):
                        return uuid.UUID(uuid_string)
                    elif hasattr(uuid_string, 'hex'):
                        return uuid_string  # Ya es un UUID
                    else:
                        logger.warning(f"Valor inválido para {field_name}: {uuid_string}")
                        return None
                except ValueError as e:
                    logger.error(f"Error convirtiendo UUID para {field_name}: {uuid_string} - {e}")
                    return None
            
            sync_config.django_event_id = safe_uuid_convert(result['event']['id'], 'event_id')
            sync_config.django_organizer_id = safe_uuid_convert(result['organizer']['id'], 'organizer_id')
            if result.get('form'):
                sync_config.django_form_id = safe_uuid_convert(result['form']['id'], 'form_id')
            
            sync_config.last_sync_at = timezone.now()
            sync_config.last_sync_status = 'success'
            sync_config.total_syncs += 1
            sync_config.successful_syncs += 1
            sync_config.save()
            
            # Actualizar ejecución con validación robusta de datos
            execution.status = 'success'
            summary = result.get('summary', {})
            
            def safe_count(value):
                """Obtiene el conteo de forma segura, manejando listas o enteros"""
                if isinstance(value, list):
                    return len(value)
                elif isinstance(value, int):
                    return value
                else:
                    return 0
            
            # Asegurar que los valores sean enteros válidos
            execution.orders_processed = safe_count(summary.get('migrated_orders', [])) + safe_count(summary.get('updated_orders', []))
            execution.tickets_processed = safe_count(summary.get('migrated_tickets', [])) + safe_count(summary.get('updated_tickets', []))
            execution.orders_created = safe_count(summary.get('migrated_orders', []))
            execution.orders_updated = safe_count(summary.get('updated_orders', []))
            execution.tickets_created = safe_count(summary.get('migrated_tickets', []))
            execution.tickets_updated = safe_count(summary.get('updated_tickets', []))
            execution.finished_at = timezone.now()
            execution.save()
            
            logger.info(f"Sincronización exitosa: {sync_config.name}")
            
            return {
                'success': True,
                'sync_config_id': sync_config_id,
                'execution_id': str(execution.id),
                'orders_processed': execution.orders_processed,
                'tickets_processed': execution.tickets_processed
            }
        else:
            raise Exception(f"Error en migración: {result['error']}")
            
    except Exception as exc:
        logger.error(f"Error en sincronización {sync_config_id}: {exc}")
        logger.error(traceback.format_exc())
        
        # Actualizar configuración
        if 'sync_config' in locals():
            sync_config.last_sync_status = 'failed'
            sync_config.total_syncs += 1
            sync_config.save()
        
        # Actualizar ejecución
        if execution:
            execution.status = 'failed'
            execution.error_message = str(exc)
            execution.finished_at = timezone.now()
            execution.save()
        
        # Reintentar si es posible
        if self.request.retries < self.max_retries:
            logger.info(f"Reintentando sincronización en {self.default_retry_delay} segundos")
            raise self.retry(exc=exc)
        
        # Notificar a administradores si fallan todos los reintentos
        mail_admins(
            f"Error en sincronización WooCommerce: {sync_config.name if 'sync_config' in locals() else sync_config_id}",
            f"Error: {exc}\n\nTraceback:\n{traceback.format_exc()}"
        )
        
        return {
            'success': False,
            'sync_config_id': sync_config_id,
            'error': str(exc)
        }


@shared_task
def run_scheduled_syncs():
    """
    Tarea que ejecuta todas las sincronizaciones programadas que están pendientes
    
    Esta tarea se ejecuta periódicamente (cada 15 minutos) para verificar
    qué sincronizaciones deben ejecutarse según su frecuencia configurada.
    """
    
    logger.info("Verificando sincronizaciones programadas")
    
    # Obtener configuraciones activas que necesitan sincronización
    configs_to_sync = SyncConfiguration.objects.filter(
        status='active'
    ).exclude(frequency='manual')
    
    syncs_triggered = 0
    
    for config in configs_to_sync:
        if config.is_due_for_sync():
            logger.info(f"Disparando sincronización programada: {config.name}")
            
            # Disparar tarea de sincronización
            sync_woocommerce_event.delay(
                str(config.id),
                trigger='scheduled'
            )
            syncs_triggered += 1
    
    logger.info(f"Sincronizaciones disparadas: {syncs_triggered}")
    return {
        'syncs_triggered': syncs_triggered,
        'timestamp': timezone.now().isoformat()
    }


@shared_task
def cleanup_old_executions():
    """
    Tarea de mantenimiento que limpia ejecuciones antiguas
    
    Mantiene solo las últimas 100 ejecuciones por configuración
    y elimina ejecuciones más antiguas de 90 días.
    """
    
    logger.info("Iniciando limpieza de ejecuciones antiguas")
    
    # Eliminar ejecuciones más antiguas de 90 días
    cutoff_date = timezone.now() - timedelta(days=90)
    old_executions = SyncExecution.objects.filter(started_at__lt=cutoff_date)
    deleted_count = old_executions.count()
    old_executions.delete()
    
    # Mantener solo las últimas 100 ejecuciones por configuración
    configs = SyncConfiguration.objects.all()
    for config in configs:
        executions = config.executions.order_by('-started_at')[100:]
        if executions:
            execution_ids = [exec.id for exec in executions]
            SyncExecution.objects.filter(id__in=execution_ids).delete()
    
    logger.info(f"Limpieza completada: {deleted_count} ejecuciones eliminadas")
    return {
        'deleted_count': deleted_count,
        'timestamp': timezone.now().isoformat()
    }


def extract_woocommerce_data(product_id: int) -> Dict[str, Any]:
    """
    Extrae datos de WooCommerce para un producto específico
    
    Args:
        product_id: ID del producto en WooCommerce
        
    Returns:
        Dict con datos extraídos (product_info, orders, tickets)
    """
    
    logger.info(f"Extrayendo datos de WooCommerce para producto {product_id}")
    
    # Obtener configuración de Django
    sync_config = get_sync_config()
    
    # Usar context manager para gestión automática de conexión
    with SSHMySQLHandler(sync_config.ssh, sync_config.mysql) as db:
        # Extraer información del producto
        product_data = db.get_product_info(product_id)
        logger.info(f"Product data recibida: {type(product_data)} - {product_data}")
        
        if not product_data:
            raise Exception(f"Producto {product_id} no encontrado en WooCommerce")
        
        # ✅ FIX: Manejar tanto dict como list
        if isinstance(product_data, list):
            if len(product_data) == 0:
                raise Exception(f"Producto {product_id} no encontrado en WooCommerce (lista vacía)")
            product_info = product_data[0]  # Tomar el primer elemento
        elif isinstance(product_data, dict):
            product_info = product_data  # Ya es un dict
        else:
            raise Exception(f"Formato inesperado de product_data: {type(product_data)}")
        
        # Extraer órdenes
        orders_data = db.get_orders_by_product_id(product_id)
        logger.info(f"Extraídas {len(orders_data)} órdenes")
        
        # Extraer tickets
        tickets_data = db.get_tickets_by_product_id(product_id)
        logger.info(f"Extraídos {len(tickets_data)} tickets")
        
        # Estructurar datos
        return {
            'product_info': {
                'product_id': product_id,
                'product_name': product_info.get('product_name', ''),
                'product_description': product_info.get('product_description', ''),
                'product_status': product_info.get('product_status', 'publish')
            },
            'orders': orders_data,
            'tickets': tickets_data
        }


@shared_task
def test_woocommerce_connection():
    """
    Tarea de prueba para verificar la conectividad con WooCommerce
    
    Returns:
        Dict con resultado de la prueba
    """
    
    try:
        logger.info("Probando conexión con WooCommerce")
        
        # Obtener configuración de Django
        sync_config = get_sync_config()
        
        # Usar context manager para gestión automática de conexión
        with SSHMySQLHandler(sync_config.ssh, sync_config.mysql) as db:
            # Probar query simple
            result = db.execute_mysql_query("SELECT 1 as test")
            
            if result and len(result) > 0:
                logger.info("Conexión con WooCommerce exitosa")
                return {
                    'success': True,
                    'message': 'Conexión exitosa',
                    'timestamp': timezone.now().isoformat()
                }
            else:
                raise Exception("Query de prueba no retornó resultados")
                
    except Exception as exc:
        logger.error(f"Error probando conexión WooCommerce: {exc}")
        return {
            'success': False,
            'error': str(exc),
            'timestamp': timezone.now().isoformat()
        }
