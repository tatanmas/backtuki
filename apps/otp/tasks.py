"""
Celery task for sending OTP emails asynchronously.
Avoids HTTP timeout when SMTP is slow or unreachable.
"""

import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_otp_email_task(self, otp_id, flow_id=None):
    """
    Send OTP email in background. If flow_id is set, logs EMAIL_SENT or EMAIL_FAILED to the flow.
    """
    try:
        from .services import OTPService
        ok = OTPService.send_email_for_otp_id(otp_id)
        if ok:
            logger.info(f"OTP email sent for otp_id={otp_id}")
        else:
            logger.warning(f"OTP email not sent for otp_id={otp_id} (expired/used or send failed)")

        if flow_id:
            try:
                from core.flow_logger import FlowLogger
                fl = FlowLogger.from_flow_id(flow_id)
                if fl and fl.flow:
                    if ok:
                        fl.log_event('EMAIL_SENT', source='celery', status='success', message='OTP email enviado correctamente')
                        fl.complete(message='OTP email sent successfully')
                    else:
                        fl.log_event('EMAIL_FAILED', source='celery', status='failure', message='Fallo envío OTP (expired/used or send failed)')
                        fl.fail(message='OTP email delivery failed')
            except Exception as e:
                logger.warning("FlowLogger update after OTP send failed (non-blocking): %s", e)

        return {'sent': ok, 'otp_id': otp_id}
    except Exception as exc:
        if flow_id:
            try:
                from core.flow_logger import FlowLogger
                fl = FlowLogger.from_flow_id(flow_id)
                if fl and fl.flow:
                    fl.log_event('EMAIL_FAILED', source='celery', status='failure', message=str(exc), metadata={'error': str(exc)})
                    fl.fail(message='OTP email delivery failed', error=exc)
            except Exception as e2:
                logger.warning("FlowLogger fail on exception (non-blocking): %s", e2)
        logger.exception(f"Error sending OTP email for otp_id={otp_id}: {exc}")
        raise self.retry(exc=exc)
