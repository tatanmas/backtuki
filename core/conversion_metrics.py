"""
🚀 ENTERPRISE: Conversion Metrics Service

Calculates historical conversion rates for each step in platform flows,
enabling comparison of individual transactions vs platform averages.
"""

from django.db.models import Count, Q, F
from django.utils import timezone
from datetime import timedelta, datetime
from core.models import PlatformFlow, PlatformFlowEvent
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


# 📅 START DATE FOR RELIABLE METRICS
# All historical statistics will be calculated ONLY from this date onwards
CONVERSION_METRICS_START_DATE = timezone.make_aware(
    datetime(2025, 12, 2, 0, 0, 0)
)


# Define the expected step sequence for ticket_checkout flows
TICKET_CHECKOUT_STEPS = [
    'RESERVATION_REQUESTED',
    'RESERVATION_CREATED',
    'ORDER_CREATED',
    'ORDER_MARKED_PAID',
    'PAYMENT_INITIATED',
    'PAYMENT_AUTHORIZED',
    'TICKETS_CREATED',
    'EMAIL_TASK_ENQUEUED',
    'EMAIL_SENT',
    'FLOW_COMPLETED',
]


class ConversionMetricsService:
    """
    Service for calculating conversion rates at each step of platform flows.
    """
    
    @staticmethod
    def get_historical_conversion_rates(
        flow_type: str = 'ticket_checkout',
        days_back: int = 30,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        organizer_id: Optional[str] = None,
        event_id: Optional[str] = None
    ) -> Dict[str, Dict]:
        """
        Calculate historical conversion rates for each step.
        
        Args:
            flow_type: Type of flow to analyze (default: 'ticket_checkout')
            days_back: Number of days to look back (default: 30)
            from_date: Optional start date for filtering flows
            to_date: Optional end date for filtering flows
            organizer_id: Optional organizer filter
            event_id: Optional event filter
            
        Returns:
            Dictionary with step names as keys and conversion metrics as values:
            {
                'RESERVATION_REQUESTED': {
                    'reached_count': 100,
                    'conversion_rate': 1.0,  # 100% (first step)
                    'previous_step': None
                },
                'ORDER_CREATED': {
                    'reached_count': 80,
                    'conversion_rate': 0.8,  # 80% of RESERVATION_CREATED
                    'previous_step': 'RESERVATION_CREATED'
                },
                ...
            }
        """
        try:
            # 🚨 IMPORTANT:
            # If from_date is provided, we respect it STRICTLY
            # If to_date is provided, we use it as the end date
            # Otherwise we fallback to a relative window (days_back)
            if from_date is not None:
                cutoff_date = from_date
            else:
                cutoff_date = timezone.now() - timedelta(days=days_back)
            
            # Base queryset for flows
            flows_qs = PlatformFlow.objects.filter(
                flow_type=flow_type,
                created_at__gte=cutoff_date
            )
            
            # Add to_date filter if provided
            if to_date is not None:
                flows_qs = flows_qs.filter(created_at__lte=to_date)
            
            if organizer_id:
                flows_qs = flows_qs.filter(organizer_id=organizer_id)
            if event_id:
                flows_qs = flows_qs.filter(event_id=event_id)
            
            flow_ids = list(flows_qs.values_list('id', flat=True))
            
            if not flow_ids:
                return {}
            
            # Get all events for these flows, grouped by step
            events_qs = PlatformFlowEvent.objects.filter(
                flow_id__in=flow_ids,
                step__in=TICKET_CHECKOUT_STEPS
            )
            
            # Count how many flows reached each step
            step_counts = {}
            for step in TICKET_CHECKOUT_STEPS:
                # Count unique flows that have this step
                reached_count = events_qs.filter(step=step).values('flow_id').distinct().count()
                step_counts[step] = reached_count
            
            # Calculate conversion rates
            conversion_rates = {}
            previous_step = None
            
            for step in TICKET_CHECKOUT_STEPS:
                reached_count = step_counts.get(step, 0)
                
                if previous_step is None:
                    # First step: 100% conversion (all flows start here)
                    conversion_rate = 1.0
                else:
                    previous_count = step_counts.get(previous_step, 0)
                    if previous_count > 0:
                        conversion_rate = reached_count / previous_count
                    else:
                        conversion_rate = 0.0
                
                conversion_rates[step] = {
                    'reached_count': reached_count,
                    'conversion_rate': round(conversion_rate, 4),  # 4 decimal places
                    'conversion_percentage': round(conversion_rate * 100, 2),
                    'previous_step': previous_step,
                    'previous_count': step_counts.get(previous_step, 0) if previous_step else None
                }
                
                previous_step = step
            
            return conversion_rates
            
        except Exception as e:
            logger.error(f"❌ [CONVERSION] Error calculating historical rates: {e}", exc_info=True)
            return {}
    
    @staticmethod
    def get_flow_conversion_metrics(flow_id: str) -> Dict[str, Dict]:
        """
        Get conversion metrics for a specific flow.
        
        Args:
            flow_id: UUID of the PlatformFlow
            
        Returns:
            Dictionary with step names as keys and metrics as values:
            {
                'RESERVATION_REQUESTED': {
                    'reached': True,
                    'timestamp': '2025-12-01T18:00:00Z',
                    'status': 'success'
                },
                ...
            }
        """
        try:
            flow = PlatformFlow.objects.get(id=flow_id)
            events = flow.events.filter(step__in=TICKET_CHECKOUT_STEPS).order_by('created_at')
            
            # Create a map of step -> event
            step_events = {event.step: event for event in events}
            
            metrics = {}
            for step in TICKET_CHECKOUT_STEPS:
                event = step_events.get(step)
                metrics[step] = {
                    'reached': event is not None,
                    'timestamp': event.created_at.isoformat() if event else None,
                    'status': event.status if event else None,
                    'message': event.message if event else None
                }
            
            return metrics
            
        except PlatformFlow.DoesNotExist:
            logger.warning(f"⚠️ [CONVERSION] Flow {flow_id} not found")
            return {}
        except Exception as e:
            logger.error(f"❌ [CONVERSION] Error getting flow metrics: {e}", exc_info=True)
            return {}
    
    @staticmethod
    def get_order_conversion_comparison(order_number: str) -> Dict:
        """
        Get conversion metrics for a specific order compared to historical averages.
        
        Args:
            order_number: Order number (e.g., 'ORD-123456')
            
        Returns:
            {
                'order_number': 'ORD-123456',
                'flow_id': 'uuid',
                'steps': [
                    {
                        'step': 'RESERVATION_REQUESTED',
                        'step_display': 'Reservation Requested',
                        'reached': True,
                        'timestamp': '2025-12-01T18:00:00Z',
                        'status': 'success',
                        'historical': {
                            'conversion_rate': 1.0,
                            'conversion_percentage': 100.0,
                            'reached_count': 1000
                        },
                        'comparison': {
                            'vs_average': 0.0,  # Same as average (100% vs 100%)
                            'status': 'normal'  # 'normal', 'above_average', 'below_average'
                        }
                    },
                    ...
                ],
                'overall_conversion': 0.85,  # This flow's overall conversion
                'historical_average': 0.82  # Historical average
            }
        """
        try:
            from apps.events.models import Order
            
            order = Order.objects.select_related('flow', 'event', 'event__organizer').get(
                order_number=order_number
            )
            
            if not order.flow:
                return {
                    'success': False,
                    'message': 'Order does not have an associated flow'
                }
            
            # Get this flow's metrics
            flow_metrics = ConversionMetricsService.get_flow_conversion_metrics(str(order.flow.id))
            
            # Get historical averages
            organizer_id = str(order.event.organizer.id) if order.event and order.event.organizer else None
            event_id = str(order.event.id) if order.event else None
            # Historical averages - using last 30 days by default
            historical_rates = ConversionMetricsService.get_historical_conversion_rates(
                flow_type='ticket_checkout',
                days_back=30,
                organizer_id=organizer_id,
                event_id=event_id
            )
            
            # Determine if this is a "legacy" order created before metrics start date
            is_legacy_order = order.created_at < CONVERSION_METRICS_START_DATE

            # Helper to build response payload from per-step data
            def _build_response(steps_data_local):
                # Calculate overall conversion (how many steps were reached)
                reached_steps_local = [s for s in steps_data_local if s.get('reached')]
                overall_conversion_local = len(reached_steps_local) / len(TICKET_CHECKOUT_STEPS) if TICKET_CHECKOUT_STEPS else 0.0

                # Calculate historical average (average of all step conversion rates)
                historical_avg_local = sum(
                    h.get('conversion_rate', 0.0) for h in historical_rates.values()
                ) / len(historical_rates) if historical_rates else 0.0

                return {
                    'success': True,
                    'order_number': order_number,
                    'flow_id': str(order.flow.id) if order.flow else None,
                    'flow_type': order.flow.flow_type if order.flow else 'ticket_checkout',
                    'flow_status': order.flow.status if order.flow else 'completed',
                    'steps': steps_data_local,
                    'overall_conversion': round(overall_conversion_local, 4),
                    'overall_conversion_percentage': round(overall_conversion_local * 100, 2),
                    'historical_average': round(historical_avg_local, 4),
                    'historical_average_percentage': round(historical_avg_local * 100, 2),
                    'comparison': {
                        'vs_average': round(overall_conversion_local - historical_avg_local, 4),
                        'vs_average_percentage': round((overall_conversion_local - historical_avg_local) * 100, 2),
                        'status': 'above_average' if overall_conversion_local > historical_avg_local + 0.05 else (
                            'below_average' if overall_conversion_local < historical_avg_local - 0.05 else 'normal'
                        )
                    }
                }

            # 🚨 LEGACY MODE:
            # For orders created BEFORE CONVERSION_METRICS_START_DATE **or** without a flow,
            # we assume the full funnel was completed successfully so they don't distort stats
            # or appear as failures due to missing tracking.
            if is_legacy_order or not order.flow:
                steps_data_legacy = []
                step_display_map = dict(PlatformFlowEvent.STEP_CHOICES)

                for step in TICKET_CHECKOUT_STEPS:
                    historical = historical_rates.get(step, {})
                    historical_rate = historical.get('conversion_rate', 0.0)

                    flow_rate = 1.0  # Legacy orders are treated as 100% success for all steps
                    vs_average = flow_rate - historical_rate
                    status_flag = 'normal'
                    if vs_average > 0.05:
                        status_flag = 'above_average'
                    elif vs_average < -0.05:
                        status_flag = 'below_average'

                    steps_data_legacy.append({
                        'step': step,
                        'step_display': step_display_map.get(step, step),
                        'reached': True,
                        'timestamp': order.created_at.isoformat() if order.created_at else None,
                        'status': 'success',
                        'message': 'Legacy order before tracking system; assumed successful.',
                        'historical': {
                            'conversion_rate': historical_rate,
                            'conversion_percentage': historical.get('conversion_percentage', 0.0),
                            'reached_count': historical.get('reached_count', 0),
                            'previous_count': historical.get('previous_count')
                        },
                        'comparison': {
                            'flow_rate': flow_rate,
                            'vs_average': round(vs_average, 4),
                            'vs_average_percentage': round(vs_average * 100, 2),
                            'status': status_flag
                        }
                    })

                return _build_response(steps_data_legacy)

            # ✅ NORMAL MODE:
            # Build step-by-step comparison using real flow events
            steps_data = []
            step_display_map = dict(PlatformFlowEvent.STEP_CHOICES)

            for step in TICKET_CHECKOUT_STEPS:
                flow_step = flow_metrics.get(step, {})
                historical = historical_rates.get(step, {})

                reached = flow_step.get('reached', False)

                # Calculate comparison
                historical_rate = historical.get('conversion_rate', 0.0)
                vs_average = 0.0
                status_flag = 'normal'

                if reached:
                    # This flow reached this step (100% for this flow)
                    flow_rate = 1.0
                    vs_average = flow_rate - historical_rate
                    if vs_average > 0.05:  # 5% threshold
                        status_flag = 'above_average'
                    elif vs_average < -0.05:
                        status_flag = 'below_average'
                else:
                    # This flow did not reach this step (0% for this flow)
                    flow_rate = 0.0
                    vs_average = flow_rate - historical_rate
                    status_flag = 'below_average'

                steps_data.append({
                    'step': step,
                    'step_display': step_display_map.get(step, step),
                    'reached': reached,
                    'timestamp': flow_step.get('timestamp'),
                    'status': flow_step.get('status'),
                    'message': flow_step.get('message'),
                    'historical': {
                        'conversion_rate': historical_rate,
                        'conversion_percentage': historical.get('conversion_percentage', 0.0),
                        'reached_count': historical.get('reached_count', 0),
                        'previous_count': historical.get('previous_count')
                    },
                    'comparison': {
                        'flow_rate': flow_rate,
                        'vs_average': round(vs_average, 4),
                        'vs_average_percentage': round(vs_average * 100, 2),
                        'status': status_flag
                    }
                })

            return _build_response(steps_data)
            
        except Order.DoesNotExist:
            return {
                'success': False,
                'message': f'Order {order_number} not found'
            }
        except Exception as e:
            logger.error(f"❌ [CONVERSION] Error getting order comparison: {e}", exc_info=True)
            return {
                'success': False,
                'message': f'Error calculating conversion metrics: {str(e)}'
            }

