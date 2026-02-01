"""
SuperAdmin Revenue Migration Views
Endpoints para migración de datos de revenue.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db.models import Count, Q
import logging

from apps.events.models import Order

from ..permissions import IsSuperUser

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def revenue_migration_status(request):
    """
    🚀 ENTERPRISE: Get status of revenue migration (how many orders need migration).
    
    GET /api/v1/superadmin/revenue-migration/status/
    
    Returns:
        - Total paid orders
        - Orders with effective values
        - Orders without effective values
        - Migration percentage
    """
    try:
        from apps.events.models import Order
        from django.db.models import Count, Q
        
        # Count all paid orders
        total_paid_orders = Order.objects.filter(status='paid').count()
        
        # Count orders with effective values
        orders_with_effective = Order.objects.filter(
            status='paid',
            subtotal_effective__isnull=False,
            service_fee_effective__isnull=False
        ).count()
        
        # Count orders without effective values
        orders_without_effective = total_paid_orders - orders_with_effective
        
        # Calculate migration percentage
        migration_percentage = (orders_with_effective / total_paid_orders * 100) if total_paid_orders > 0 else 0
        
        logger.info(f"📊 [SuperAdmin] Revenue migration status: {orders_with_effective}/{total_paid_orders} ({migration_percentage:.2f}%)")
        
        return Response({
            'success': True,
            'status': {
                'total_paid_orders': total_paid_orders,
                'orders_with_effective': orders_with_effective,
                'orders_without_effective': orders_without_effective,
                'migration_percentage': round(migration_percentage, 2),
                'is_complete': orders_without_effective == 0
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error getting revenue migration status: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error al obtener estado de migración: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsSuperUser])  # ENTERPRISE: Solo superusers
def migrate_revenue_data(request):
    """
    🚀 ENTERPRISE: Migrate revenue data for orders that don't have effective values.
    
    POST /api/v1/superadmin/revenue-migration/migrate/
    
    Body (optional):
        - batch_size: Number of orders to process per batch (default: 100)
        - dry_run: If true, don't actually migrate (default: false)
    
    Returns:
        - Total orders found
        - Orders migrated
        - Orders failed
        - Success rate
        - Errors (if any)
    """
    try:
        from apps.events.models import Order
        from core.revenue_system import migrate_order_effective_values
        from django.db import transaction
        
        batch_size = int(request.data.get('batch_size', 100))
        dry_run = request.data.get('dry_run', False)
        
        if dry_run:
            logger.info("🔍 [SuperAdmin] Revenue migration DRY RUN mode")
        
        # Get orders that need migration
        orders_to_migrate = Order.objects.filter(
            status='paid',
            subtotal_effective__isnull=True
        ).prefetch_related('items')
        
        total_orders = orders_to_migrate.count()
        
        if total_orders == 0:
            return Response({
                'success': True,
                'message': 'No hay órdenes que requieran migración',
                'summary': {
                    'total_orders': 0,
                    'migrated': 0,
                    'failed': 0,
                    'success_rate': 100.0
                }
            }, status=status.HTTP_200_OK)
        
        if dry_run:
            # Return what would be migrated without actually doing it
            sample_orders = orders_to_migrate[:5]
            sample_data = [{
                'order_number': order.order_number,
                'subtotal': float(order.subtotal),
                'service_fee': float(order.service_fee),
                'discount': float(order.discount),
                'total': float(order.total)
            } for order in sample_orders]
            
            return Response({
                'success': True,
                'dry_run': True,
                'message': f'DRY RUN: Se migrarían {total_orders} órdenes',
                'summary': {
                    'total_orders': total_orders,
                    'migrated': 0,
                    'failed': 0,
                    'success_rate': 0.0
                },
                'sample_orders': sample_data
            }, status=status.HTTP_200_OK)
        
        # Perform migration
        logger.info(f"🚀 [SuperAdmin] Starting revenue migration for {total_orders} orders (batch_size={batch_size})")
        
        migrated_count = 0
        failed_count = 0
        errors = []
        
        # Process in batches
        for i in range(0, total_orders, batch_size):
            batch = orders_to_migrate[i:i+batch_size]
            
            for order in batch:
                try:
                    with transaction.atomic():
                        success = migrate_order_effective_values(order)
                        if success:
                            migrated_count += 1
                            if migrated_count % 50 == 0:
                                logger.info(f"  📊 Progress: {migrated_count}/{total_orders} orders migrated...")
                        else:
                            failed_count += 1
                            errors.append({
                                'order_number': order.order_number,
                                'error': 'Migration returned False'
                            })
                except Exception as e:
                    failed_count += 1
                    error_msg = str(e)
                    errors.append({
                        'order_number': order.order_number,
                        'error': error_msg
                    })
                    logger.error(f"❌ [SuperAdmin] Error migrating order {order.order_number}: {error_msg}", exc_info=True)
        
        success_rate = (migrated_count / total_orders * 100) if total_orders > 0 else 0
        
        logger.info(f"✅ [SuperAdmin] Revenue migration completed: {migrated_count}/{total_orders} ({success_rate:.2f}%)")
        
        return Response({
            'success': True,
            'message': f'Migración completada: {migrated_count} exitosas, {failed_count} fallidas',
            'summary': {
                'total_orders': total_orders,
                'migrated': migrated_count,
                'failed': failed_count,
                'success_rate': round(success_rate, 2)
            },
            'errors': errors[:20] if errors else [],  # Return first 20 errors
            'total_errors': len(errors)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ [SuperAdmin] Error migrating revenue data: {str(e)}", exc_info=True)
        return Response({
            'success': False,
            'message': f'Error al migrar datos de revenue: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


