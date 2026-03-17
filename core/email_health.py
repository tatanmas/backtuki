"""
Email health check for platform monitoring.
Tests SMTP connectivity and optionally sends a test email (e.g. to the same account)
so SuperAdmin can verify that the backend can send (and optionally that mail is received).
"""

import logging
from django.conf import settings
from django.core.mail import get_connection, send_mail

logger = logging.getLogger(__name__)


def check_smtp_connection():
    """
    Test SMTP connectivity only (no email sent).
    Returns (ok: bool, message: str).
    """
    try:
        conn = get_connection(
            backend=settings.EMAIL_BACKEND,
            host=settings.EMAIL_HOST,
            port=settings.EMAIL_PORT,
            username=settings.EMAIL_HOST_USER,
            password=settings.EMAIL_HOST_PASSWORD,
            use_tls=settings.EMAIL_USE_TLS,
            use_ssl=settings.EMAIL_USE_SSL,
            timeout=getattr(settings, "EMAIL_TIMEOUT", 10),
        )
        conn.open()
        conn.close()
        return True, "SMTP connection OK"
    except Exception as e:
        logger.warning("SMTP connection check failed: %s", e)
        return False, str(e)


def check_email_send(recipient=None, skip_send=False):
    """
    Test email delivery: connect and optionally send a test message.
    If recipient is None, uses the same address as FROM (noreply@tuki.cl),
    so you can verify in webmail that the message was received.
    Returns dict: ok, message, detail, recipient_used.
    """
    recipient_used = recipient or (settings.EMAIL_HOST_USER if hasattr(settings, "EMAIL_HOST_USER") else "noreply@tuki.cl")
    # Normalize: EMAIL_HOST_USER might be "noreply@tuki.cl"
    if not recipient_used or "@" not in str(recipient_used):
        recipient_used = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@tuki.cl")
        if " <" in recipient_used:
            recipient_used = recipient_used.split(" <")[-1].rstrip(">")
        else:
            recipient_used = "noreply@tuki.cl"

    # 1) Connection test
    conn_ok, conn_msg = check_smtp_connection()
    if not conn_ok:
        return {
            "ok": False,
            "message": "SMTP connection failed",
            "detail": conn_msg,
            "recipient_used": recipient_used,
        }

    if skip_send:
        return {
            "ok": True,
            "message": "SMTP connection OK (send skipped)",
            "detail": conn_msg,
            "recipient_used": None,
        }

    # 2) Send test email
    try:
        send_mail(
            subject="[Tuki] Prueba de correo - plataforma OK",
            message="Este es un correo de prueba del sistema Tuki. Si lo recibes, el envío desde la plataforma está funcionando.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_used],
            fail_silently=False,
        )
        return {
            "ok": True,
            "message": "Test email sent successfully",
            "detail": f"Enviado a {recipient_used}. Revisa el buzón (p. ej. https://mail.tuki.cl/webmail) para confirmar recepción.",
            "recipient_used": recipient_used,
        }
    except Exception as e:
        logger.warning("Email send check failed: %s", e)
        return {
            "ok": False,
            "message": "Test email send failed",
            "detail": str(e),
            "recipient_used": recipient_used,
        }
