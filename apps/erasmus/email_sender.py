"""
🚀 ENTERPRISE Email sender for Erasmus activity payment confirmation.
Same pattern as events/experiences: sync send, flow logging, <10s latency.
"""
import logging
import os
import time
from typing import Dict, Any, Optional

from django.conf import settings
from django.core.mail import get_connection
from django.template.loader import render_to_string
from django.utils import timezone
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _activity_image_url(act) -> Optional[str]:
    """Build absolute image URL for ErasmusActivity (activity.images or linked experience). No request."""
    img_url = None
    if getattr(act, "images", None) and isinstance(act.images, list) and len(act.images) > 0:
        img = act.images[0]
        img_url = img if isinstance(img, str) else (img.get("url") or img.get("image")) if isinstance(img, dict) else None
    if not img_url and getattr(act, "experience_id", None):
        exp = getattr(act, "experience", None)
        if exp and getattr(exp, "images", None) and len(exp.images or []) > 0:
            img = (exp.images or [])[0]
            img_url = img if isinstance(img, str) else (img.get("url") if isinstance(img, dict) else None)
    if img_url and isinstance(img_url, str) and img_url.strip():
        if not (img_url.startswith("http://") or img_url.startswith("https://")):
            base = (getattr(settings, "PUBLIC_BASE_URL", None) or getattr(settings, "FRONTEND_URL", "") or "https://tuki.cl").rstrip("/")
            img_url = base + (img_url if img_url.startswith("/") else "/" + img_url)
    else:
        img_url = None
    return img_url


def send_erasmus_activity_confirmation_email_optimized(
    order_id: str,
    to_email: Optional[str] = None,
    flow_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    🚀 ENTERPRISE: Send Erasmus activity payment confirmation email (sync, same flow as events).
    """
    start_time = time.time()
    metrics = {"fetch_time_ms": 0, "context_time_ms": 0, "render_time_ms": 0, "smtp_time_ms": 0, "total_time_ms": 0}

    try:
        from apps.events.models import Order, EmailLog
        from apps.erasmus.email_context import build_erasmus_activity_confirmation_context
        from core.flow_logger import FlowLogger

        fetch_start = time.time()
        order = Order.objects.select_related(
            "erasmus_activity_payment_link",
            "erasmus_activity_payment_link__lead",
            "erasmus_activity_payment_link__instance",
            "erasmus_activity_payment_link__instance__activity",
            "erasmus_activity_payment_link__instance__activity__experience",
        ).get(id=order_id)
        metrics["fetch_time_ms"] = int((time.time() - fetch_start) * 1000)

        if order.status != "paid":
            logger.warning(f"📧 [EMAIL_ERASMUS] Order {order.order_number} not paid, skipping")
            return {"status": "skipped", "reason": "order_not_paid", "metrics": metrics}

        link = getattr(order, "erasmus_activity_payment_link", None)
        if not link:
            logger.warning(f"📧 [EMAIL_ERASMUS] No payment link for order {order.order_number}")
            return {"status": "skipped", "reason": "no_link", "metrics": metrics}

        act = link.instance.activity
        image_url = _activity_image_url(act)

        context_start = time.time()
        context = build_erasmus_activity_confirmation_context(order, link, image_url=image_url)
        metrics["context_time_ms"] = int((time.time() - context_start) * 1000)

        recipient_email = to_email or context.get("customer_email", "") or order.email
        if not recipient_email or "@" not in recipient_email:
            logger.warning(f"📧 [EMAIL_ERASMUS] No valid email for order {order.order_number}")
            return {"status": "skipped", "reason": "no_email", "metrics": metrics}

        render_start = time.time()
        html_message = render_to_string("emails/erasmus/confirmation.html", context)
        text_message = render_to_string("emails/erasmus/confirmation.txt", context)
        metrics["render_time_ms"] = int((time.time() - render_start) * 1000)

        activity_title = context.get("activity_title", "Actividad Erasmus")
        subject = f"✅ Pago confirmado - {activity_title}"
        from_email = settings.DEFAULT_FROM_EMAIL

        root_msg = MIMEMultipart("mixed")
        root_msg["Subject"] = subject
        root_msg["From"] = from_email
        root_msg["To"] = recipient_email

        alternative_msg = MIMEMultipart("alternative")
        alternative_msg.attach(MIMEText(text_message, "plain", "utf-8"))
        related_msg = MIMEMultipart("related")
        related_msg.attach(MIMEText(html_message, "html", "utf-8"))

        logo_path = os.path.join(settings.BASE_DIR, "static/images/logos/logo-negro.png")
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as f:
                logo = MIMEImage(f.read())
                logo.add_header("Content-ID", "<logo_negro>")
                logo.add_header("Content-Disposition", "inline")
                related_msg.attach(logo)
        isotipo_path = os.path.join(settings.BASE_DIR, "static/images/logos/isotipo-azul.png")
        if os.path.exists(isotipo_path):
            with open(isotipo_path, "rb") as f:
                iso = MIMEImage(f.read())
                iso.add_header("Content-ID", "<isotipo_azul>")
                iso.add_header("Content-Disposition", "inline")
                related_msg.attach(iso)

        alternative_msg.attach(related_msg)
        root_msg.attach(alternative_msg)

        email_log = EmailLog.objects.create(
            order=order,
            to_email=recipient_email,
            subject=subject,
            template="erasmus_activity_confirmation",
            status="pending",
            attempts=1,
            metadata={"order_number": order.order_number, "activity_title": activity_title},
        )

        class _MIMEWrapper:
            def __init__(self, m):
                self._m = m
            def as_bytes(self, linesep=None):
                return self._m.as_bytes()
            def __getattr__(self, name):
                return getattr(self._m, name)

        class _CustomEmailMessage:
            def __init__(self, mime, from_e, to_e):
                self._mime = _MIMEWrapper(mime)
                self.from_email = from_e
                self.to = [to_e] if isinstance(to_e, str) else to_e
                self._recipients = self.to
                self.encoding = "utf-8"
                self.cc = []
                self.bcc = []
                self.reply_to = []
                self.extra_headers = {}
                self.attachments = []
            def message(self):
                return self._mime
            def recipients(self):
                return self._recipients
            def get_connection(self, fail_silently):
                return get_connection(fail_silently=fail_silently)

        smtp_start = time.time()
        connection = get_connection(fail_silently=False)
        connection.send_messages([_CustomEmailMessage(root_msg, from_email, recipient_email)])
        metrics["smtp_time_ms"] = int((time.time() - smtp_start) * 1000)

        email_log.status = "sent"
        email_log.sent_at = timezone.now()
        email_log.save(update_fields=["status", "sent_at"])

        logger.info(f"✅ [EMAIL_ERASMUS] Sent to {recipient_email} in {metrics['smtp_time_ms']}ms")

        if flow_id:
            fl = FlowLogger.from_flow_id(flow_id)
            if fl and fl.flow:
                fl.log_event(
                    "EMAIL_SENT",
                    order=order,
                    email_log=email_log,
                    status="success",
                    message=f"Email sent to {recipient_email}",
                    metadata={
                        "recipient": recipient_email,
                        "smtp_time_ms": metrics["smtp_time_ms"],
                        "context_time_ms": metrics["context_time_ms"],
                        "render_time_ms": metrics["render_time_ms"],
                    },
                )

        metrics["total_time_ms"] = int((time.time() - start_time) * 1000)
        return {"status": "success", "emails_sent": 1, "recipient": recipient_email, "metrics": metrics}

    except Exception as e:
        metrics["total_time_ms"] = int((time.time() - start_time) * 1000)
        logger.error(f"❌ [EMAIL_ERASMUS] Error for order {order_id}: {e}", exc_info=True)
        if flow_id:
            try:
                from core.flow_logger import FlowLogger
                fl = FlowLogger.from_flow_id(flow_id)
                if fl and fl.flow:
                    fl.log_event("EMAIL_FAILED", status="error", message=f"Email failed: {str(e)}", metadata={"error": str(e), "metrics": metrics})
            except Exception as le:
                logger.error(f"❌ [EMAIL_ERASMUS] Failed to log to flow: {le}")
        return {"status": "error", "error": str(e), "metrics": metrics}
