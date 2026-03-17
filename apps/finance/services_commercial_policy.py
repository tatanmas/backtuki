"""Commercial policy resolution service.

Resolves the applicable CommercialPolicy for a given organizer, vertical, and product
using priority + scope hierarchy: product > vertical_default > organizer_default.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

if TYPE_CHECKING:
    from apps.organizers.models import Organizer

from .models import CommercialPolicy

logger = logging.getLogger('finance.commercial_policy')


_DEFAULT_POLICY_SNAPSHOT = {
    'commercial_mode': 'collect_total',
    'recognition_policy': 'on_settlement_close',
    'settlement_policy': 'manual',
}


def resolve_commercial_policy(
    *,
    organizer: Organizer,
    product_type: str | None = None,
    product_id: str | None = None,
    as_of: date | None = None,
) -> CommercialPolicy | None:
    """Return the highest-priority active policy that matches the given scope.

    Resolution order (first match wins):
    1. product-level policy  (scope_type='product', scope_id=product_id)
    2. vertical-level policy (scope_type='vertical_default', scope_id based on product_type)
    3. organizer-level policy (scope_type='organizer_default', organizer=organizer)
    """
    as_of = as_of or timezone.localdate()

    base_qs = CommercialPolicy.objects.filter(
        is_active=True,
        effective_from__lte=as_of,
    ).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=as_of),
    ).order_by('-priority', '-effective_from')

    if product_id:
        policy = base_qs.filter(scope_type='product', scope_id=product_id).first()
        if policy:
            logger.debug('Resolved product-level policy %s for product %s', policy.id, product_id)
            return policy

    if product_type:
        policy = base_qs.filter(
            scope_type='vertical_default',
            organizer=organizer,
            metadata__vertical=product_type,
        ).first()
        if policy:
            logger.debug('Resolved vertical-level policy %s for %s/%s', policy.id, organizer.id, product_type)
            return policy

    policy = base_qs.filter(
        scope_type='organizer_default',
        organizer=organizer,
    ).first()

    if policy:
        logger.debug('Resolved organizer-level policy %s for %s', policy.id, organizer.id)
    else:
        logger.debug('No policy found for organizer %s; will use system defaults', organizer.id)

    return policy


def snapshot_policy(policy: CommercialPolicy | None) -> dict:
    """Serialize a policy to a JSON-safe dict for embedding as a snapshot."""
    if policy is None:
        return dict(_DEFAULT_POLICY_SNAPSHOT)
    return {
        'id': str(policy.id),
        'scope_type': policy.scope_type,
        'scope_id': str(policy.scope_id) if policy.scope_id else None,
        'commercial_mode': policy.commercial_mode,
        'recognition_policy': policy.recognition_policy,
        'settlement_policy': policy.settlement_policy,
        'effective_from': policy.effective_from.isoformat(),
        'effective_to': policy.effective_to.isoformat() if policy.effective_to else None,
        'priority': policy.priority,
    }


def get_effective_commercial_mode(policy: CommercialPolicy | None) -> str:
    """Return the commercial mode from a resolved policy, or the system default."""
    if policy:
        return policy.commercial_mode
    return _DEFAULT_POLICY_SNAPSHOT['commercial_mode']
