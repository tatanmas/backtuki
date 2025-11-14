"""
Vistas de la API para sincronización WooCommerce
"""

import logging
from datetime import datetime, timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)
from django.db.models import Count, Q, Avg
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import SyncConfiguration, SyncExecution, SyncCredentials
from .serializers import (
    SyncConfigurationSerializer,
    SyncConfigurationCreateSerializer,
    SyncExecutionSerializer,
    SyncCredentialsSerializer,
    SyncTriggerSerializer,
    SyncStatsSerializer,
    SyncTestConnectionSerializer
)
from .tasks import sync_woocommerce_event, test_woocommerce_connection

logger = logging.getLogger(__name__)


class SyncConfigurationViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar configuraciones de sincronización
    
    Endpoints:
    - GET /api/v1/sync-woocommerce/configurations/ - Listar configuraciones
    - POST /api/v1/sync-woocommerce/configurations/ - Crear configuración
    - GET /api/v1/sync-woocommerce/configurations/{id}/ - Obtener configuración
    - PUT/PATCH /api/v1/sync-woocommerce/configurations/{id}/ - Actualizar configuración
    - DELETE /api/v1/sync-woocommerce/configurations/{id}/ - Eliminar configuración
    - POST /api/v1/sync-woocommerce/configurations/{id}/trigger/ - Disparar sincronización
    - POST /api/v1/sync-woocommerce/configurations/{id}/pause/ - Pausar sincronización
    - POST /api/v1/sync-woocommerce/configurations/{id}/resume/ - Reanudar sincronización
    """
    
    queryset = SyncConfiguration.objects.all()
    permission_classes = [AllowAny]  # 🚀 Sin autenticación para Super Admin
    throttle_classes = []  # 🚀 Sin rate limiting para sincronización WooCommerce
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'frequency', 'organizer_email']
    search_fields = ['name', 'event_name', 'organizer_email']
    ordering_fields = ['created_at', 'updated_at', 'last_sync_at', 'name']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Usar serializer específico para creación"""
        if self.action == 'create':
            return SyncConfigurationCreateSerializer
        return SyncConfigurationSerializer
    
    def perform_create(self, serializer):
        """Asignar usuario creador al crear configuración"""
        # Para Super Admin sin autenticación, usar None si es usuario anónimo
        created_by = None if self.request.user.is_anonymous else self.request.user
        serializer.save(created_by=created_by)
    
    @action(detail=True, methods=['post'])
    def trigger(self, request, pk=None):
        """
        Disparar sincronización manual
        
        POST /api/v1/sync-woocommerce/configurations/{id}/trigger/
        """
        config = self.get_object()
        
        logger.info(f"🔵 TRIGGER RECIBIDO - Config: {config.name} (ID: {config.id}), Status: {config.status}")
        
        if config.status not in ['active', 'paused']:
            logger.warning(f"⚠️ Trigger rechazado - Status inválido: {config.status}")
            return Response(
                {'error': 'La configuración debe estar activa o pausada'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Log de info importante ANTES de disparar
        from django.conf import settings
        logger.info(f"📤 Enviando tarea a Celery:")
        logger.info(f"   - Broker: {settings.CELERY_BROKER_URL}")
        logger.info(f"   - Config ID: {config.id}")
        logger.info(f"   - Event Name: {config.event_name}")
        logger.info(f"   - WooCommerce Product ID: {config.woocommerce_product_id}")
        logger.info(f"   - Cola: sync-heavy (concurrency=1, solo 1 sync a la vez)")
        
        # Disparar tarea de Celery
        task = sync_woocommerce_event.delay(
            str(config.id),
            trigger='manual',
            user_id=request.user.id
        )
        
        logger.info(f"✅ Tarea Celery creada - Task ID: {task.id}")
        logger.info(f"   - Usuario: {request.user.username}")
        logger.info(f"   - Config: {config.name}")
        logger.info(f"   - La tarea está en cola 'sync-heavy' esperando ser procesada")
        logger.info(f"   💡 Si hay otra sync ejecutándose, esta esperará automáticamente")
        
        return Response({
            'message': 'Sincronización iniciada',
            'task_id': task.id,
            'config_id': str(config.id),
            'config_name': config.name
        })
    
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """
        Pausar sincronización
        
        POST /api/v1/sync-woocommerce/configurations/{id}/pause/
        """
        config = self.get_object()
        
        if config.status != 'active':
            return Response(
                {'error': 'Solo se pueden pausar configuraciones activas'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        config.status = 'paused'
        config.save()
        
        logger.info(f"Sincronización pausada por {request.user.username}: {config.name}")
        
        return Response({
            'message': 'Sincronización pausada',
            'config_id': str(config.id),
            'status': config.status
        })
    
    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        """
        Reanudar sincronización
        
        POST /api/v1/sync-woocommerce/configurations/{id}/resume/
        """
        config = self.get_object()
        
        if config.status != 'paused':
            return Response(
                {'error': 'Solo se pueden reanudar configuraciones pausadas'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        config.status = 'active'
        config.save()
        
        logger.info(f"Sincronización reanudada por {request.user.username}: {config.name}")
        
        return Response({
            'message': 'Sincronización reanudada',
            'config_id': str(config.id),
            'status': config.status
        })
    
    @action(detail=True, methods=['get'])
    def executions(self, request, pk=None):
        """
        Obtener ejecuciones de una configuración específica
        
        GET /api/v1/sync-woocommerce/configurations/{id}/executions/
        """
        config = self.get_object()
        executions = config.executions.all()[:50]  # Últimas 50 ejecuciones
        
        serializer = SyncExecutionSerializer(executions, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """
        Probar conexión con WooCommerce para una configuración específica
        
        POST /api/v1/sync-woocommerce/configurations/{id}/test_connection/
        """
        config = self.get_object()
        
        try:
            # Importar aquí para evitar problemas de importación circular
            from .tasks import test_woocommerce_connection
            
            # Ejecutar test de conexión de forma síncrona para respuesta inmediata
            result = test_woocommerce_connection.apply()
            
            return Response({
                'success': result.successful() if result else False,
                'message': 'Test de conexión completado',
                'details': result.result if result and result.successful() else {},
                'config_id': str(config.id)
            })
            
        except Exception as e:
            logger.error(f"Error probando conexión para config {config.id}: {e}")
            return Response({
                'success': False,
                'error': str(e),
                'config_id': str(config.id)
            }, status=500)


class SyncExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para ver ejecuciones de sincronización (solo lectura)
    
    Endpoints:
    - GET /api/v1/sync-woocommerce/executions/ - Listar ejecuciones
    - GET /api/v1/sync-woocommerce/executions/{id}/ - Obtener ejecución
    """
    
    queryset = SyncExecution.objects.all()
    serializer_class = SyncExecutionSerializer
    permission_classes = [AllowAny]  # 🚀 Sin autenticación para Super Admin
    throttle_classes = []  # 🚀 Sin rate limiting
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'trigger', 'configuration']
    search_fields = ['configuration__name', 'error_message']
    ordering_fields = ['started_at', 'finished_at', 'duration_seconds']
    ordering = ['-started_at']
    
    def get_queryset(self):
        """Filtrar ejecuciones de los últimos 30 días por defecto"""
        queryset = super().get_queryset()
        
        # Filtrar por fecha si se especifica
        days = self.request.query_params.get('days')
        if days:
            try:
                days = int(days)
                cutoff_date = timezone.now() - timedelta(days=days)
                queryset = queryset.filter(started_at__gte=cutoff_date)
            except ValueError:
                pass
        else:
            # Por defecto, últimos 30 días
            cutoff_date = timezone.now() - timedelta(days=30)
            queryset = queryset.filter(started_at__gte=cutoff_date)
        
        return queryset


class SyncCredentialsViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar credenciales de sincronización
    
    Endpoints:
    - GET /api/v1/sync-woocommerce/credentials/ - Listar credenciales
    - POST /api/v1/sync-woocommerce/credentials/ - Crear credenciales
    - GET /api/v1/sync-woocommerce/credentials/{id}/ - Obtener credenciales
    - PUT/PATCH /api/v1/sync-woocommerce/credentials/{id}/ - Actualizar credenciales
    - DELETE /api/v1/sync-woocommerce/credentials/{id}/ - Eliminar credenciales
    """
    
    queryset = SyncCredentials.objects.all()
    serializer_class = SyncCredentialsSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'is_default']
    search_fields = ['name', 'ssh_host', 'mysql_database']
    ordering_fields = ['name', 'created_at']
    ordering = ['-is_default', 'name']


class SyncManagementViewSet(viewsets.ViewSet):
    """
    ViewSet para operaciones de gestión de sincronización
    
    Endpoints:
    - GET /api/v1/sync-woocommerce/management/stats/ - Estadísticas generales
    - POST /api/v1/sync-woocommerce/management/test-connection/ - Probar conexión
    - POST /api/v1/sync-woocommerce/management/trigger-all/ - Disparar todas las sincronizaciones
    - POST /api/v1/sync-woocommerce/management/cleanup/ - Limpiar ejecuciones antiguas
    """
    
    permission_classes = [AllowAny]  # 🚀 Sin autenticación para Super Admin
    throttle_classes = []  # 🚀 Sin rate limiting
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Obtener estadísticas generales del sistema de sincronización
        
        GET /api/v1/sync-woocommerce/management/stats/
        """
        
        # Estadísticas de configuraciones
        config_stats = SyncConfiguration.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='active')),
            paused=Count('id', filter=Q(status='paused')),
            disabled=Count('id', filter=Q(status='disabled')),
            error=Count('id', filter=Q(status='error'))
        )
        
        # Estadísticas de ejecuciones de hoy
        today = timezone.now().date()
        today_executions = SyncExecution.objects.filter(
            started_at__date=today
        ).aggregate(
            total=Count('id'),
            successful=Count('id', filter=Q(status='success')),
            failed=Count('id', filter=Q(status='failed'))
        )
        
        # Estadísticas de ejecuciones de la semana
        week_ago = timezone.now() - timedelta(days=7)
        week_executions = SyncExecution.objects.filter(
            started_at__gte=week_ago
        ).aggregate(
            total=Count('id'),
            successful=Count('id', filter=Q(status='success')),
            failed=Count('id', filter=Q(status='failed'))
        )
        
        # Tasa de éxito promedio
        avg_success_rate = SyncConfiguration.objects.filter(
            total_syncs__gt=0
        ).aggregate(
            avg_rate=Avg('successful_syncs') * 100 / Avg('total_syncs')
        )['avg_rate'] or 0
        
        # Configuraciones que necesitan sincronización
        configs_due = sum(1 for config in SyncConfiguration.objects.filter(status='active') if config.is_due_for_sync())
        
        stats_data = {
            'total_configurations': config_stats['total'],
            'active_configurations': config_stats['active'],
            'paused_configurations': config_stats['paused'],
            'disabled_configurations': config_stats['disabled'],
            'error_configurations': config_stats['error'],
            
            'total_executions_today': today_executions['total'],
            'successful_executions_today': today_executions['successful'],
            'failed_executions_today': today_executions['failed'],
            
            'total_executions_week': week_executions['total'],
            'successful_executions_week': week_executions['successful'],
            'failed_executions_week': week_executions['failed'],
            
            'average_success_rate': round(avg_success_rate, 2),
            'configurations_due_for_sync': configs_due
        }
        
        serializer = SyncStatsSerializer(stats_data)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def test_connection(self, request):
        """
        Probar conexión con WooCommerce
        
        POST /api/v1/sync-woocommerce/management/test-connection/
        """
        serializer = SyncTestConnectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Disparar tarea de prueba
        task = test_woocommerce_connection.delay()
        
        # Esperar resultado (máximo 30 segundos)
        try:
            result = task.get(timeout=30)
            return Response(result)
        except Exception as exc:
            return Response({
                'success': False,
                'error': str(exc),
                'task_id': task.id
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def trigger_all(self, request):
        """
        Disparar todas las sincronizaciones activas manualmente
        
        POST /api/v1/sync-woocommerce/management/trigger-all/
        """
        active_configs = SyncConfiguration.objects.filter(status='active')
        
        # Manejar usuario anónimo para Super Admin
        user_id = None if request.user.is_anonymous else request.user.id
        username = 'SuperAdmin' if request.user.is_anonymous else request.user.username
        
        logger.info(f"🔵 TRIGGER ALL recibido por {username}")
        logger.info(f"   - Configs activas encontradas: {active_configs.count()}")
        
        from django.conf import settings
        logger.info(f"📤 Broker Celery: {settings.CELERY_BROKER_URL}")
        logger.info(f"   Cola: sync-heavy (concurrency=1, las syncs se procesarán una por una)")
        
        triggered_tasks = []
        for config in active_configs:
            logger.info(f"   📝 Disparando: {config.name} (ID: {config.id})")
            
            task = sync_woocommerce_event.delay(
                str(config.id),
                trigger='api',
                user_id=user_id
            )
            
            logger.info(f"      ✅ Task ID: {task.id}")
            
            triggered_tasks.append({
                'config_id': str(config.id),
                'config_name': config.name,
                'event_name': config.event_name,
                'task_id': task.id
            })
        
        logger.info(f"🚀 RESUMEN: {len(triggered_tasks)} sincronizaciones enviadas a cola 'sync-heavy' por {username}")
        logger.info(f"   💡 Se procesarán una por una para evitar problemas de memoria")
        logger.info(f"   Las tareas están en Redis y se ejecutarán automáticamente cuando haya capacidad")
        
        return Response({
            'message': f'{len(triggered_tasks)} sincronizaciones iniciadas',
            'tasks': triggered_tasks
        })
    
    @action(detail=False, methods=['post'])
    def cleanup(self, request):
        """
        Limpiar ejecuciones antiguas manualmente
        
        POST /api/v1/sync-woocommerce/management/cleanup/
        """
        from .tasks import cleanup_old_executions
        
        task = cleanup_old_executions.delay()
        
        return Response({
            'message': 'Limpieza iniciada',
            'task_id': task.id
        })
    
    @action(detail=False, methods=['post'])
    def purge_queue(self, request):
        """
        Purgar (eliminar) todas las tareas pendientes en la cola sync-heavy
        
        POST /api/v1/sync-woocommerce/management/purge-queue/
        
        ⚠️ CUIDADO: Esto elimina TODAS las syncs pendientes irrecuperablemente
        """
        from celery import current_app
        
        queue_name = request.data.get('queue', 'sync-heavy')
        
        try:
            # Purgar la cola especificada
            current_app.control.purge()
            
            logger.warning(f"🗑️ Cola '{queue_name}' purgada por SuperAdmin")
            
            return Response({
                'message': f"Cola '{queue_name}' purgada exitosamente",
                'warning': 'Todas las tareas pendientes han sido eliminadas'
            })
        except Exception as e:
            logger.error(f"Error purgando cola: {e}")
            return Response({
                'error': str(e)
            }, status=500)
    
    @action(detail=False, methods=['get'])
    def queue_status(self, request):
        """
        Ver estado de las colas de Celery
        
        GET /api/v1/sync-woocommerce/management/queue-status/
        """
        from celery import current_app
        from celery.app.control import Inspect
        
        try:
            i = Inspect(app=current_app)
            
            # Obtener información de los workers
            active_tasks = i.active()
            reserved_tasks = i.reserved()
            scheduled_tasks = i.scheduled()
            stats = i.stats()
            
            return Response({
                'workers': {
                    'active_tasks': active_tasks or {},
                    'reserved_tasks': reserved_tasks or {},
                    'scheduled_tasks': scheduled_tasks or {},
                    'stats': stats or {}
                },
                'queues': {
                    'sync-heavy': {
                        'description': 'Cola dedicada para syncs pesadas (concurrency=1)'
                    },
                    'default': {
                        'description': 'Cola general'
                    }
                }
            })
        except Exception as e:
            logger.error(f"Error obteniendo estado de colas: {e}")
            return Response({
                'error': str(e),
                'message': 'No se pudo conectar con los workers de Celery'
            }, status=500)
