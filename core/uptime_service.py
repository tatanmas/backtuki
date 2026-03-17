"""
Servicio de uptime basado en heartbeats en BD.

- Considera "downtime" cuando hay un hueco > DOWNTIME_GAP_SECONDS entre dos heartbeats.
- Calcula % uptime y lista de incidentes (cuándo no estuvo arriba).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from django.utils import timezone

# Si entre dos heartbeats pasan más de 2 minutos, se considera downtime
DOWNTIME_GAP_SECONDS = 120


@dataclass
class DowntimeIncident:
    """Intervalo en que la plataforma se consideró caída."""
    started_at: datetime
    ended_at: datetime
    duration_seconds: float


@dataclass
class UptimeReport:
    """Reporte de uptime para un periodo."""
    period_start: datetime
    period_end: datetime
    total_seconds: float
    uptime_seconds: float
    downtime_seconds: float
    uptime_percent: float
    incidents: List[DowntimeIncident]
    last_heartbeat_at: Optional[datetime]
    is_currently_up: bool
    current_run_started_at: Optional[datetime]
    """Inicio del tramo actual 'arriba' (tras el último downtime)."""
    current_run_seconds: Optional[float]
    """Segundos desde current_run_started_at hasta now (uptime del tramo actual)."""


def get_heartbeats_in_range(
    start: timezone.datetime,
    end: timezone.datetime,
    order_asc: bool = True,
):
    from core.models import PlatformUptimeHeartbeat

    qs = PlatformUptimeHeartbeat.objects.filter(
        recorded_at__gte=start,
        recorded_at__lte=end,
    ).order_by("recorded_at" if order_asc else "-recorded_at")
    return list(qs.values_list("recorded_at", flat=True))


def compute_downtime_incidents(
    heartbeats: List[timezone.datetime],
    gap_seconds: int = DOWNTIME_GAP_SECONDS,
) -> List[DowntimeIncident]:
    """A partir de una lista ordenada de timestamps, devuelve los intervalos de downtime."""
    incidents = []
    for i in range(1, len(heartbeats)):
        prev, curr = heartbeats[i - 1], heartbeats[i]
        gap = (curr - prev).total_seconds()
        if gap > gap_seconds:
            incidents.append(
                DowntimeIncident(
                    started_at=prev,
                    ended_at=curr,
                    duration_seconds=gap,
                )
            )
    return incidents


def get_last_heartbeat() -> Optional[timezone.datetime]:
    from core.models import PlatformUptimeHeartbeat

    last = PlatformUptimeHeartbeat.objects.order_by("-recorded_at").values_list("recorded_at", flat=True).first()
    return last


def get_last_heartbeat_source() -> Optional[str]:
    """Origen del último heartbeat (celery, health, platform_status, management_command). Para indicar en UI si los datos son fiables."""
    from core.models import PlatformUptimeHeartbeat

    row = (
        PlatformUptimeHeartbeat.objects.order_by("-recorded_at")
        .values_list("source", flat=True)
        .first()
    )
    return row


def record_heartbeat_if_throttled(
    min_interval_seconds: int = 55,
    source: str = "health",
) -> bool:
    """
    Registra un heartbeat solo si el último es más antiguo que min_interval_seconds.
    Usado por el endpoint de health (load balancer/Cloud Run) para que el uptime
    refleje disponibilidad real aunque Celery Beat no esté escribiendo.
    Devuelve True si se escribió un nuevo heartbeat.
    """
    from core.models import PlatformUptimeHeartbeat

    last = get_last_heartbeat()
    now = timezone.now()
    if last is not None and (now - last).total_seconds() < min_interval_seconds:
        return False
    try:
        PlatformUptimeHeartbeat.objects.create(recorded_at=now, source=source)
        return True
    except Exception:
        return False


def get_current_run_start(
    before: Optional[timezone.datetime] = None,
    gap_seconds: int = DOWNTIME_GAP_SECONDS,
) -> Optional[timezone.datetime]:
    """
    Devuelve el inicio del tramo actual "arriba".
    Busca hacia atrás desde `before` (o now) hasta encontrar un hueco > gap_seconds.
    """
    from core.models import PlatformUptimeHeartbeat

    end = before or timezone.now()
    # Heartbeats recientes ordenados descendente
    heartbeats = list(
        PlatformUptimeHeartbeat.objects.filter(recorded_at__lte=end)
        .order_by("-recorded_at")
        .values_list("recorded_at", flat=True)[:500]
    )
    if not heartbeats:
        return None
    # Orden ascendente para iterar del más viejo al más reciente
    heartbeats = list(reversed(heartbeats))
    run_start = heartbeats[0]
    for i in range(1, len(heartbeats)):
        prev, curr = heartbeats[i - 1], heartbeats[i]
        if (curr - prev).total_seconds() > gap_seconds:
            run_start = curr
    return run_start


def get_uptime_report(
    period_hours: int = 24,
    gap_seconds: int = DOWNTIME_GAP_SECONDS,
) -> UptimeReport:
    """
    Genera el reporte de uptime para las últimas `period_hours` horas.
    """
    from core.models import PlatformUptimeHeartbeat

    period_end = timezone.now()
    period_start = period_end - timedelta(hours=period_hours)
    total_seconds = (period_end - period_start).total_seconds()

    heartbeats = get_heartbeats_in_range(period_start, period_end, order_asc=True)
    incidents = compute_downtime_incidents(heartbeats, gap_seconds)

    # Downtime = suma de duraciones de huecos (dentro del periodo)
    downtime_seconds = 0.0
    for inc in incidents:
        # Recortar al periodo si aplica
        start = max(inc.started_at, period_start)
        end = min(inc.ended_at, period_end)
        if start < end:
            downtime_seconds += (end - start).total_seconds()
    uptime_seconds = max(0.0, total_seconds - downtime_seconds)
    uptime_percent = (uptime_seconds / total_seconds * 100.0) if total_seconds > 0 else 0.0

    last_hb = get_last_heartbeat()
    consider_down_after = timedelta(seconds=gap_seconds)
    is_currently_up = last_hb is not None and (period_end - last_hb) <= consider_down_after

    current_run_started_at = get_current_run_start(before=period_end, gap_seconds=gap_seconds)
    current_run_seconds = None
    if current_run_started_at:
        current_run_seconds = (period_end - current_run_started_at).total_seconds()

    return UptimeReport(
        period_start=period_start,
        period_end=period_end,
        total_seconds=total_seconds,
        uptime_seconds=uptime_seconds,
        downtime_seconds=downtime_seconds,
        uptime_percent=uptime_percent,
        incidents=incidents,
        last_heartbeat_at=last_hb,
        is_currently_up=is_currently_up,
        current_run_started_at=current_run_started_at,
        current_run_seconds=current_run_seconds,
    )
