"""
🚀 ENTERPRISE REVENUE SYSTEM
============================

This module is the SINGLE SOURCE OF TRUTH for all revenue calculations in the platform.

Key Principles:
1. All revenue calculations MUST use functions from this module
2. Values are calculated ONCE at purchase time and stored in the database
3. All monetary values are integers (no decimals for CLP)
4. Discounts are distributed proportionally between organizer revenue and platform fees
5. Multiple validation layers ensure data integrity

Data Model:
-----------
Order:
  - subtotal: Original organizer revenue (before discount)
  - service_fee: Original platform commission (before discount)
  - discount: Total discount applied (from coupon)
  - total: Final amount paid by customer (after discount)
  - subtotal_effective: Effective organizer revenue (after proportional discount)
  - service_fee_effective: Effective platform commission (after proportional discount)
  
  INVARIANT: subtotal_effective + service_fee_effective = total

OrderItem:
  - unit_price: Original unit price (before discount)
  - unit_service_fee: Original unit service fee (before discount)
  - subtotal: (unit_price + unit_service_fee) × quantity
  - unit_price_effective: Effective unit price (after proportional discount)
  - unit_service_fee_effective: Effective unit service fee (after proportional discount)
  - subtotal_effective: (unit_price_effective + unit_service_fee_effective) × quantity

Coupon:
  - discount_type: 'percentage' or 'fixed'
  - discount_value: Percentage (0-100) or fixed amount
  - calculate_discount_amount(amount): Returns discount as integer

Usage:
------
# At purchase time (in BookingSerializer):
from core.revenue_system import calculate_and_store_effective_values
calculate_and_store_effective_values(order)

# For analytics/reporting:
from core.revenue_system import get_event_revenue, get_ticket_tier_revenue
revenue = get_event_revenue(event, start_date, end_date)
"""

from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum, Count, Q
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# CORE CALCULATION FUNCTIONS
# ============================================================================

def calculate_effective_values(subtotal, service_fee, discount):
    """
    🚀 ENTERPRISE: Calculate effective values after proportional discount distribution.
    
    This is the CORE algorithm that distributes discounts fairly between
    organizer revenue and platform commission.
    
    Args:
        subtotal (Decimal): Original organizer revenue (before discount)
        service_fee (Decimal): Original platform commission (before discount)
        discount (Decimal): Total discount to apply
    
    Returns:
        tuple: (subtotal_effective, service_fee_effective, total)
        
    Example:
        subtotal = 1000, service_fee = 150, discount = 230
        total_original = 1150
        payment_ratio = (1150 - 230) / 1150 = 0.8
        subtotal_effective = 1000 × 0.8 = 800
        service_fee_effective = 150 × 0.8 = 120
        total = 920
        Validation: 800 + 120 = 920 ✅
    """
    # Convert to Decimal for precision
    subtotal = Decimal(str(subtotal))
    service_fee = Decimal(str(service_fee))
    discount = Decimal(str(discount))
    
    # Calculate original total
    total_original = subtotal + service_fee
    
    # Calculate final total after discount
    total_final = total_original - discount
    total_final = max(Decimal('0'), total_final)  # Never negative
    
    # Round to integer (CLP has no decimals)
    total_final = total_final.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    
    if discount == 0 or total_original == 0:
        # No discount or zero total - effective = original
        subtotal_effective = subtotal.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        service_fee_effective = service_fee.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    else:
        # Calculate payment ratio
        payment_ratio = total_final / total_original
        
        # Distribute proportionally
        subtotal_effective = (subtotal * payment_ratio).quantize(
            Decimal('1'), rounding=ROUND_HALF_UP
        )
        service_fee_effective = (service_fee * payment_ratio).quantize(
            Decimal('1'), rounding=ROUND_HALF_UP
        )
        
        # Adjust for rounding errors to ensure exact sum
        calculated_total = subtotal_effective + service_fee_effective
        if calculated_total != total_final:
            # Adjust service_fee_effective to make sum exact
            service_fee_effective = total_final - subtotal_effective
            
            # Log if adjustment was significant (more than 1 CLP)
            if abs(calculated_total - total_final) > 1:
                logger.warning(
                    f"Revenue calculation rounding adjustment: "
                    f"calculated={calculated_total}, expected={total_final}, "
                    f"adjustment={total_final - calculated_total}"
                )
    
    return subtotal_effective, service_fee_effective, total_final


def calculate_and_store_effective_values(order):
    """
    🚀 ENTERPRISE: Calculate and store effective values for an order and its items.
    
    This function should be called ONCE when an order is created, right after
    the discount is applied. It calculates the effective values and stores them
    in the database.
    
    Args:
        order: Order instance (must be saved to DB with items already created)
    
    Returns:
        dict: Summary of calculated values
        
    Raises:
        ValueError: If order validation fails
    """
    from apps.events.models import OrderItem
    
    # Validate order has required fields
    if order.subtotal is None or order.service_fee is None:
        raise ValueError("Order must have subtotal and service_fee set")
    
    # Calculate effective values at order level
    subtotal_effective, service_fee_effective, total_final = calculate_effective_values(
        order.subtotal,
        order.service_fee,
        order.discount
    )
    
    # Store in order
    order.subtotal_effective = subtotal_effective
    order.service_fee_effective = service_fee_effective
    order.total = total_final
    order.save(update_fields=['subtotal_effective', 'service_fee_effective', 'total'])
    
    # Calculate payment ratio for items
    total_original = order.subtotal + order.service_fee
    if total_original > 0 and order.discount > 0:
        payment_ratio = Decimal(str(total_final)) / Decimal(str(total_original))
    else:
        payment_ratio = Decimal('1')
    
    # Calculate effective values for each item
    items_summary = []
    for item in order.items.all():
        # Calculate effective unit prices
        unit_price_effective = (Decimal(str(item.unit_price)) * payment_ratio).quantize(
            Decimal('1'), rounding=ROUND_HALF_UP
        )
        unit_service_fee_effective = (Decimal(str(item.unit_service_fee)) * payment_ratio).quantize(
            Decimal('1'), rounding=ROUND_HALF_UP
        )
        subtotal_effective_item = (unit_price_effective + unit_service_fee_effective) * item.quantity
        
        # Store in item
        item.unit_price_effective = unit_price_effective
        item.unit_service_fee_effective = unit_service_fee_effective
        item.subtotal_effective = subtotal_effective_item
        item.save(update_fields=[
            'unit_price_effective',
            'unit_service_fee_effective',
            'subtotal_effective'
        ])
        
        items_summary.append({
            'ticket_tier': item.ticket_tier.name,
            'quantity': item.quantity,
            'unit_price_effective': float(unit_price_effective),
            'unit_service_fee_effective': float(unit_service_fee_effective),
            'subtotal_effective': float(subtotal_effective_item)
        })
    
    # Validate: sum of items should equal order total
    items_total = sum(item.subtotal_effective for item in order.items.all())
    if abs(items_total - total_final) > 1:  # Allow 1 CLP difference for rounding
        logger.error(
            f"Order {order.order_number} validation FAILED: "
            f"items_total={items_total}, order_total={total_final}, "
            f"difference={abs(items_total - total_final)}"
        )
        raise ValueError(
            f"Items total ({items_total}) doesn't match order total ({total_final})"
        )
    
    logger.info(
        f"✅ Order {order.order_number} effective values calculated: "
        f"gross_revenue={subtotal_effective}, service_fees={service_fee_effective}, "
        f"total={total_final}, discount={order.discount}"
    )
    
    return {
        'order_number': order.order_number,
        'subtotal_effective': float(subtotal_effective),
        'service_fee_effective': float(service_fee_effective),
        'total': float(total_final),
        'discount': float(order.discount),
        'items': items_summary,
        'validation': 'passed'
    }


# ============================================================================
# REVENUE QUERY FUNCTIONS
# ============================================================================

def get_event_revenue(event, start_date=None, end_date=None, validate=True):
    """
    🚀 ENTERPRISE: Get revenue metrics for an event.
    
    This function uses the stored effective values (preferred method) with
    fallback to proportional calculation for backward compatibility.
    
    Args:
        event: Event instance
        start_date: Optional start date filter
        end_date: Optional end date filter
        validate: If True, performs cross-validation
    
    Returns:
        dict: Revenue metrics
    """
    from apps.events.models import Order, OrderItem
    
    # Build queryset
    orders = Order.objects.filter(event=event, status='paid')
    
    if start_date:
        orders = orders.filter(created_at__gte=start_date)
    if end_date:
        orders = orders.filter(created_at__lte=end_date)
    
    # Try to use effective fields (preferred method)
    revenue_data = orders.aggregate(
        total_revenue=Sum('total'),
        gross_revenue=Sum('subtotal_effective'),
        service_fees=Sum('service_fee_effective'),
        subtotal_original=Sum('subtotal'),
        service_fees_original=Sum('service_fee'),
        total_discount=Sum('discount'),
        total_orders=Count('id')
    )
    
    # Check if effective fields are populated
    if revenue_data['gross_revenue'] is not None:
        # ✅ Effective fields exist - use them (most robust)
        result = {
            'total_revenue': float(revenue_data['total_revenue'] or 0),
            'gross_revenue': float(revenue_data['gross_revenue'] or 0),
            'service_fees': float(revenue_data['service_fees'] or 0),
            'subtotal_original': float(revenue_data['subtotal_original'] or 0),
            'service_fees_original': float(revenue_data['service_fees_original'] or 0),
            'total_discount': float(revenue_data['total_discount'] or 0),
            'total_orders': revenue_data['total_orders'] or 0,
            'calculation_method': 'stored_effective_values'
        }
    else:
        # ⚠️ Fallback: Calculate proportionally (backward compatibility)
        logger.warning(
            f"Event {event.id} has orders without effective fields. "
            f"Using fallback calculation method."
        )
        
        total_revenue = float(revenue_data['total_revenue'] or 0)
        subtotal_original = float(revenue_data['subtotal_original'] or 0)
        service_fees_original = float(revenue_data['service_fees_original'] or 0)
        total_original = subtotal_original + service_fees_original
        
        if total_original > 0:
            payment_ratio = Decimal(str(total_revenue)) / Decimal(str(total_original))
            gross_revenue = (Decimal(str(subtotal_original)) * payment_ratio).quantize(
                Decimal('1'), rounding=ROUND_HALF_UP
            )
            service_fees = (Decimal(str(service_fees_original)) * payment_ratio).quantize(
                Decimal('1'), rounding=ROUND_HALF_UP
            )
        else:
            gross_revenue = Decimal('0')
            service_fees = Decimal('0')
        
        result = {
            'total_revenue': total_revenue,
            'gross_revenue': float(gross_revenue),
            'service_fees': float(service_fees),
            'subtotal_original': subtotal_original,
            'service_fees_original': service_fees_original,
            'total_discount': float(revenue_data['total_discount'] or 0),
            'total_orders': revenue_data['total_orders'] or 0,
            'calculation_method': 'proportional_fallback'
        }
    
    # Add tickets count
    tickets_data = OrderItem.objects.filter(
        order__in=orders
    ).aggregate(
        total_tickets=Sum('quantity')
    )
    result['total_tickets'] = tickets_data['total_tickets'] or 0
    
    # Validation
    if validate:
        validation_result = validate_revenue_calculation(orders, result)
        result['validation'] = validation_result
    
    return result


def get_ticket_tier_revenue(ticket_tier, start_date=None, end_date=None, validate=True):
    """
    🚀 ENTERPRISE: Get revenue metrics for a specific ticket tier.
    
    For multi-tier orders, this distributes revenue proportionally based on
    the tier's share of the order.
    
    Args:
        ticket_tier: TicketTier instance
        start_date: Optional start date filter
        end_date: Optional end date filter
        validate: If True, performs cross-validation
    
    Returns:
        dict: Revenue metrics for the tier
    """
    from apps.events.models import Order, OrderItem
    
    # Get orders containing this tier
    orders = Order.objects.filter(
        items__ticket_tier=ticket_tier,
        status='paid'
    ).distinct()
    
    if start_date:
        orders = orders.filter(created_at__gte=start_date)
    if end_date:
        orders = orders.filter(created_at__lte=end_date)
    
    # Calculate tier's share of each order
    tier_revenue = Decimal('0')
    tier_gross_revenue = Decimal('0')
    tier_service_fees = Decimal('0')
    tier_tickets = 0
    
    for order in orders:
        # Get all items in this order
        order_items = order.items.all()
        total_items = sum(item.quantity for item in order_items)
        
        # Get this tier's items
        tier_items = order_items.filter(ticket_tier=ticket_tier)
        tier_quantity = sum(item.quantity for item in tier_items)
        
        if total_items == 0:
            continue
        
        # Calculate tier's share
        tier_share = Decimal(str(tier_quantity)) / Decimal(str(total_items))
        
        # Use effective values if available
        if order.subtotal_effective is not None:
            tier_order_revenue = Decimal(str(order.total)) * tier_share
            tier_order_gross = Decimal(str(order.subtotal_effective)) * tier_share
            tier_order_fees = Decimal(str(order.service_fee_effective)) * tier_share
        else:
            # Fallback to proportional calculation
            tier_order_revenue = Decimal(str(order.total)) * tier_share
            tier_order_subtotal = Decimal(str(order.subtotal)) * tier_share
            tier_order_service_fee = Decimal(str(order.service_fee)) * tier_share
            tier_order_original = tier_order_subtotal + tier_order_service_fee
            
            if tier_order_original > 0:
                payment_ratio = tier_order_revenue / tier_order_original
                tier_order_gross = (tier_order_subtotal * payment_ratio).quantize(
                    Decimal('1'), rounding=ROUND_HALF_UP
                )
                tier_order_fees = (tier_order_service_fee * payment_ratio).quantize(
                    Decimal('1'), rounding=ROUND_HALF_UP
                )
            else:
                tier_order_gross = Decimal('0')
                tier_order_fees = Decimal('0')
        
        tier_revenue += tier_order_revenue
        tier_gross_revenue += tier_order_gross
        tier_service_fees += tier_order_fees
        tier_tickets += tier_quantity
    
    # Round to integers
    tier_revenue = tier_revenue.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    tier_gross_revenue = tier_gross_revenue.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    tier_service_fees = tier_service_fees.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    
    result = {
        'total_revenue': float(tier_revenue),
        'gross_revenue': float(tier_gross_revenue),
        'service_fees': float(tier_service_fees),
        'total_tickets': tier_tickets,
        'total_orders': orders.count(),
        'ticket_tier_name': ticket_tier.name,
        'ticket_tier_id': ticket_tier.id
    }
    
    return result


def get_organizer_revenue(organizer, start_date=None, end_date=None):
    """
    🚀 ENTERPRISE: Get total revenue metrics for an organizer across all events.
    
    Args:
        organizer: Organizer instance
        start_date: Optional start date filter
        end_date: Optional end date filter
    
    Returns:
        dict: Aggregated revenue metrics
    """
    from apps.events.models import Event
    
    # Get all events for this organizer
    events = Event.objects.filter(organizer=organizer)
    
    # Aggregate revenue from all events
    total_revenue = 0
    total_gross_revenue = 0
    total_service_fees = 0
    total_tickets = 0
    total_orders = 0
    
    for event in events:
        event_revenue = get_event_revenue(event, start_date, end_date, validate=False)
        total_revenue += event_revenue['total_revenue']
        total_gross_revenue += event_revenue['gross_revenue']
        total_service_fees += event_revenue['service_fees']
        total_tickets += event_revenue['total_tickets']
        total_orders += event_revenue['total_orders']
    
    return {
        'total_revenue': total_revenue,
        'gross_revenue': total_gross_revenue,
        'service_fees': total_service_fees,
        'total_tickets': total_tickets,
        'total_orders': total_orders,
        'total_events': events.count()
    }


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_revenue_calculation(orders_queryset, calculated_result):
    """
    🚀 ENTERPRISE: Validate revenue calculation using multiple methods.
    
    This performs cross-validation to ensure data integrity:
    1. Sum of effective values = total revenue
    2. Sum from orders = sum from items
    3. All effective values are present (no NULL)
    
    Args:
        orders_queryset: QuerySet of Order objects
        calculated_result: Dict with calculated revenue metrics
    
    Returns:
        dict: Validation result with status and details
    """
    from apps.events.models import OrderItem
    
    validation = {
        'status': 'passed',
        'checks': [],
        'warnings': [],
        'errors': []
    }
    
    # Check 1: Effective values sum to total
    expected_total = calculated_result['total_revenue']
    calculated_total = calculated_result['gross_revenue'] + calculated_result['service_fees']
    diff = abs(expected_total - calculated_total)
    
    if diff <= 1:  # Allow 1 CLP difference for rounding
        validation['checks'].append({
            'name': 'effective_values_sum',
            'status': 'passed',
            'message': f"Effective values sum correctly: {calculated_total} ≈ {expected_total}"
        })
    else:
        validation['status'] = 'failed'
        validation['errors'].append({
            'name': 'effective_values_sum',
            'message': f"Effective values don't sum: {calculated_total} ≠ {expected_total} (diff: {diff})"
        })
    
    # Check 2: Sum from items equals sum from orders
    items_total = OrderItem.objects.filter(
        order__in=orders_queryset
    ).aggregate(
        total=Sum('subtotal_effective')
    )['total']
    
    if items_total is not None:
        items_diff = abs(float(items_total) - expected_total)
        if items_diff <= orders_queryset.count():  # Allow 1 CLP per order for rounding
            validation['checks'].append({
                'name': 'items_vs_orders',
                'status': 'passed',
                'message': f"Items sum matches orders: {items_total} ≈ {expected_total}"
            })
        else:
            validation['warnings'].append({
                'name': 'items_vs_orders',
                'message': f"Items sum differs from orders: {items_total} ≠ {expected_total} (diff: {items_diff})"
            })
    
    # Check 3: All orders have effective values
    orders_without_effective = orders_queryset.filter(
        Q(subtotal_effective__isnull=True) | Q(service_fee_effective__isnull=True)
    ).count()
    
    if orders_without_effective == 0:
        validation['checks'].append({
            'name': 'effective_fields_present',
            'status': 'passed',
            'message': "All orders have effective values"
        })
    else:
        validation['warnings'].append({
            'name': 'effective_fields_present',
            'message': f"{orders_without_effective} orders missing effective values (using fallback calculation)"
        })
    
    return validation


# ============================================================================
# MIGRATION HELPERS
# ============================================================================

def migrate_order_effective_values(order):
    """
    🚀 ENTERPRISE: Calculate and store effective values for an existing order.
    
    This function is used for migrating historical data. It calculates
    effective values from the original fields.
    
    Args:
        order: Order instance
    
    Returns:
        bool: True if migration was successful
    """
    try:
        # Skip if already migrated
        if order.subtotal_effective is not None:
            return True
        
        # Calculate effective values
        subtotal_effective, service_fee_effective, total_final = calculate_effective_values(
            order.subtotal,
            order.service_fee,
            order.discount
        )
        
        # Store in order
        order.subtotal_effective = subtotal_effective
        order.service_fee_effective = service_fee_effective
        order.save(update_fields=['subtotal_effective', 'service_fee_effective'])
        
        # Calculate for items
        if order.discount > 0:
            total_original = order.subtotal + order.service_fee
            payment_ratio = Decimal(str(total_final)) / Decimal(str(total_original))
        else:
            payment_ratio = Decimal('1')
        
        for item in order.items.all():
            unit_price_effective = (Decimal(str(item.unit_price)) * payment_ratio).quantize(
                Decimal('1'), rounding=ROUND_HALF_UP
            )
            unit_service_fee_effective = (Decimal(str(item.unit_service_fee)) * payment_ratio).quantize(
                Decimal('1'), rounding=ROUND_HALF_UP
            )
            subtotal_effective_item = (unit_price_effective + unit_service_fee_effective) * item.quantity
            
            item.unit_price_effective = unit_price_effective
            item.unit_service_fee_effective = unit_service_fee_effective
            item.subtotal_effective = subtotal_effective_item
            item.save(update_fields=[
                'unit_price_effective',
                'unit_service_fee_effective',
                'subtotal_effective'
            ])
        
        logger.info(f"✅ Migrated order {order.order_number}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to migrate order {order.order_number}: {e}")
        return False


def migrate_all_orders(batch_size=100):
    """
    🚀 ENTERPRISE: Migrate all existing orders to use effective values.
    
    This function processes orders in batches to avoid memory issues.
    
    Args:
        batch_size: Number of orders to process at once
    
    Returns:
        dict: Migration summary
    """
    from apps.events.models import Order
    
    orders_to_migrate = Order.objects.filter(
        subtotal_effective__isnull=True,
        status='paid'
    )
    
    total_orders = orders_to_migrate.count()
    migrated = 0
    failed = 0
    
    logger.info(f"Starting migration of {total_orders} orders...")
    
    for i in range(0, total_orders, batch_size):
        batch = orders_to_migrate[i:i+batch_size]
        for order in batch:
            if migrate_order_effective_values(order):
                migrated += 1
            else:
                failed += 1
        
        logger.info(f"Progress: {migrated + failed}/{total_orders} orders processed")
    
    summary = {
        'total_orders': total_orders,
        'migrated': migrated,
        'failed': failed,
        'success_rate': (migrated / total_orders * 100) if total_orders > 0 else 0
    }
    
    logger.info(f"Migration complete: {summary}")
    return summary

