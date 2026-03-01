"""
Celery tasks for WhatsApp app.
"""
import logging

from celery import shared_task
from django.utils import timezone

from apps.whatsapp.models import GroupOutreachConfig
from apps.whatsapp.services.group_outreach_service import run_outreach_for_config

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def run_group_outreach(self):
    """
    Run outreach (first message) for all enabled group configs.
    Each config sends up to max_per_run messages with human-like behavior.
    Scheduled by beat every 12 minutes to avoid spam detection.
    One failing config does not stop the rest; errors are logged and counted.
    """
    configs = list(GroupOutreachConfig.objects.filter(enabled=True).select_related("group"))
    total_sent = 0
    total_errors = 0
    for config in configs:
        try:
            result = run_outreach_for_config(config)
            total_sent += result.get("sent", 0)
            total_errors += result.get("errors", 0)
        except Exception as e:
            logger.exception("Outreach run failed for config %s (group %s): %s", config.id, config.group_id, e)
            total_errors += 1
            # Continue with next config so one bad group does not block others
    if total_sent or total_errors:
        logger.info("Group outreach run: sent=%s, errors=%s, configs=%s", total_sent, total_errors, len(configs))
    return {"sent": total_sent, "errors": total_errors}
