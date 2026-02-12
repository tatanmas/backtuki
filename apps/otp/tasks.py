"""
Celery task for sending OTP emails asynchronously.
Avoids HTTP timeout when SMTP is slow or unreachable.
"""

import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_otp_email_task(self, otp_id):
    """
    Send OTP email in background. Called after OTP is generated so the API returns immediately.
    """
    try:
        from .services import OTPService
        ok = OTPService.send_email_for_otp_id(otp_id)
        if ok:
            logger.info(f"OTP email sent for otp_id={otp_id}")
        else:
            logger.warning(f"OTP email not sent for otp_id={otp_id} (expired/used or send failed)")
        return {'sent': ok, 'otp_id': otp_id}
    except Exception as exc:
        logger.exception(f"Error sending OTP email for otp_id={otp_id}: {exc}")
        raise self.retry(exc=exc)
