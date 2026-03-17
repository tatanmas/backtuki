"""
Enterprise Organizer Wallet Service

Consolidated balance per organizer: revenue (platform collects, owes organizer)
minus OrganizerCredits (free tours - organizer owes platform) minus Payouts.

Balance = revenue - organizer_credits - payouts
- Positive: we owe organizer
- Negative: organizer owes us (e.g. overpaid, or credits from free tours)
- Supports partial/advance payments
"""

from decimal import Decimal
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce

from core.revenue_system import order_revenue_eligible_q


def get_organizer_wallet(organizer, include_breakdown=True):
    """
    Returns wallet summary for an organizer.

    Revenue sources (platform collects, owes organizer):
    - Events: paid orders only (status='paid'), subtotal_effective
    - Experiences: paid orders (customer paid)
    - Accommodations: paid orders (platform collects model)

    Deductions:
    - OrganizerCredits: free tours where organizer pays platform
    - Payouts: already transferred

    Returns:
        dict with: revenue_events, revenue_experiences, revenue_accommodations,
        total_revenue, organizer_credits, payouts_sum, balance,
        breakdown (optional) with due_date references
    """
    from apps.events.models import Order
    from apps.organizers.models import Payout

    # Revenue from paid orders only (exclude refunded, cancelled, sandbox, deleted, excluded)
    event_orders = Order.objects.filter(
        order_kind='event', event__organizer=organizer,
    ).filter(order_revenue_eligible_q())
    event_revenue = event_orders.aggregate(
        total=Sum(Coalesce('subtotal_effective', 'subtotal'))
    )['total'] or Decimal('0')

    exp_orders = Order.objects.filter(
        order_kind='experience',
        experience_reservation__experience__organizer=organizer,
    ).filter(order_revenue_eligible_q())
    exp_revenue = exp_orders.aggregate(
        total=Sum(Coalesce('subtotal_effective', 'subtotal'))
    )['total'] or Decimal('0')

    acc_orders = Order.objects.filter(
        order_kind='accommodation',
        accommodation_reservation__accommodation__organizer=organizer,
    ).filter(order_revenue_eligible_q())
    acc_revenue = acc_orders.aggregate(
        total=Sum(Coalesce('subtotal_effective', 'subtotal'))
    )['total'] or Decimal('0')

    total_revenue = event_revenue + exp_revenue + acc_revenue

    # OrganizerCredits: free tours - organizer pays platform (reduces what we owe)
    try:
        credits_sum = organizer.credits.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    except Exception:
        credits_sum = Decimal('0')

    # Payouts: already transferred
    payouts_sum = Payout.objects.filter(organizer=organizer).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')

    balance = total_revenue - credits_sum - payouts_sum

    result = {
        'revenue_events': float(event_revenue),
        'revenue_experiences': float(exp_revenue),
        'revenue_accommodations': float(acc_revenue),
        'total_revenue': float(total_revenue),
        'organizer_credits': float(credits_sum),
        'payouts_sum': float(payouts_sum),
        'balance': float(balance),
        'by_type': {
            'events': float(event_revenue),
            'experiences': float(exp_revenue),
            'accommodations': float(acc_revenue),
        },
    }

    if include_breakdown:
        result['breakdown'] = _get_breakdown(organizer)

    return result


def _get_breakdown(organizer):
    """
    Per-source breakdown with due date references.
    - Events: event end_date (when it "should have been paid")
    - Accommodations: checkout date
    - Experiences: tour instance start_datetime
    """
    from apps.events.models import Order
    from django.db.models import Sum
    from django.db.models.functions import Coalesce

    breakdown = {'events': [], 'experiences': [], 'accommodations': []}

    # Events: group by event (exclude sandbox, deleted, excluded)
    event_orders = Order.objects.filter(
        order_kind='event', event__organizer=organizer,
    ).filter(order_revenue_eligible_q()).select_related('event')
    from collections import defaultdict
    event_totals = defaultdict(lambda: {'revenue': Decimal('0'), 'orders': 0, 'end_date': None})
    for o in event_orders:
        key = o.event_id
        event_totals[key]['revenue'] += (o.subtotal_effective or o.subtotal or 0)
        event_totals[key]['orders'] += 1
        if o.event:
            event_totals[key]['end_date'] = o.event.end_date or o.event.start_date
            event_totals[key]['title'] = o.event.title
            event_totals[key]['event_id'] = str(o.event.id)
    for k, v in event_totals.items():
        breakdown['events'].append({
            'event_id': v.get('event_id'),
            'title': v.get('title', ''),
            'revenue': float(v['revenue']),
            'orders_count': v['orders'],
            'due_date_reference': v['end_date'].isoformat() if v.get('end_date') else None,
        })

    # Experiences: group by experience (exclude sandbox, deleted, excluded)
    exp_orders = Order.objects.filter(
        order_kind='experience',
        experience_reservation__experience__organizer=organizer,
    ).filter(order_revenue_eligible_q()).select_related('experience_reservation__experience', 'experience_reservation__instance')
    exp_totals = defaultdict(lambda: {'revenue': Decimal('0'), 'orders': 0, 'last_date': None})
    for o in exp_orders:
        try:
            exp = o.experience_reservation.experience if o.experience_reservation else None
            inst = o.experience_reservation.instance if o.experience_reservation else None
            key = exp.id if exp else o.id
            exp_totals[key]['revenue'] += (o.subtotal_effective or o.subtotal or 0)
            exp_totals[key]['orders'] += 1
            if inst and inst.start_datetime:
                exp_totals[key]['last_date'] = inst.start_datetime
            exp_totals[key]['title'] = exp.title if exp else ''
            exp_totals[key]['experience_id'] = str(exp.id) if exp else ''
        except Exception:
            pass
    for k, v in exp_totals.items():
        breakdown['experiences'].append({
            'experience_id': v.get('experience_id'),
            'title': v.get('title', ''),
            'revenue': float(v['revenue']),
            'orders_count': v['orders'],
            'due_date_reference': v['last_date'].isoformat() if v.get('last_date') else None,
        })

    # Accommodations: group by accommodation (exclude sandbox, deleted, excluded)
    acc_orders = Order.objects.filter(
        order_kind='accommodation',
        accommodation_reservation__accommodation__organizer=organizer,
    ).filter(order_revenue_eligible_q()).select_related('accommodation_reservation__accommodation')
    acc_totals = defaultdict(lambda: {'revenue': Decimal('0'), 'orders': 0, 'last_checkout': None})
    for o in acc_orders:
        try:
            acc = o.accommodation_reservation.accommodation if o.accommodation_reservation else None
            res = o.accommodation_reservation
            key = acc.id if acc else o.id
            acc_totals[key]['revenue'] += (o.subtotal_effective or o.subtotal or 0)
            acc_totals[key]['orders'] += 1
            if res and hasattr(res, 'check_out') and res.check_out:
                acc_totals[key]['last_checkout'] = res.check_out
            acc_totals[key]['title'] = acc.title if acc else ''
            acc_totals[key]['accommodation_id'] = str(acc.id) if acc else ''
        except Exception:
            pass
    for k, v in acc_totals.items():
        breakdown['accommodations'].append({
            'accommodation_id': v.get('accommodation_id'),
            'title': v.get('title', ''),
            'revenue': float(v['revenue']),
            'orders_count': v['orders'],
            'due_date_reference': v['last_checkout'].isoformat() if v.get('last_checkout') else None,
        })

    return breakdown


def get_all_organizer_wallets(include_zero_balance=False, include_negative=False):
    """
    All organizers with activity. By default: balance > 0 (we owe them).
    include_zero_balance: show balance = 0
    include_negative: show balance < 0 (they owe us)
    """
    from apps.organizers.models import Organizer

    organizers = Organizer.objects.prefetch_related(
        'banking_details', 'billing_details', 'payouts', 'credits'
    ).all()

    result = []
    for org in organizers:
        wallet = get_organizer_wallet(org)
        balance = wallet['balance']
        if balance > 0:
            pass  # include
        elif balance == 0 and not include_zero_balance:
            continue
        elif balance < 0 and not include_negative:
            continue

        result.append({
            'organizer_id': str(org.id),
            'organizer_name': org.name,
            'organizer_email': org.contact_email,
            **wallet,
        })

    result.sort(key=lambda x: x['balance'], reverse=True)
    return result
