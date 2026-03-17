"""Financial report endpoints for superadmin."""

from __future__ import annotations

from datetime import date

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.finance.services_reports import (
    balance_sheet,
    cash_flow_basic,
    income_statement,
    trial_balance,
)

from ..permissions import IsSuperUser


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_report_balance_sheet(request):
    as_of = _parse_date(request.query_params.get('as_of'))
    report = balance_sheet(as_of=as_of)
    return Response({'success': True, **report})


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_report_income_statement(request):
    period_start = _parse_date(request.query_params.get('period_start'))
    period_end = _parse_date(request.query_params.get('period_end'))
    report = income_statement(period_start=period_start, period_end=period_end)
    return Response({'success': True, **report})


@api_view(['GET'])
@permission_classes([IsSuperUser])
def finance_report_cash_flow(request):
    period_start = _parse_date(request.query_params.get('period_start'))
    period_end = _parse_date(request.query_params.get('period_end'))
    report = cash_flow_basic(period_start=period_start, period_end=period_end)
    return Response({'success': True, **report})
