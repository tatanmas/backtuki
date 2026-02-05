"""
Service for generating reservation confirmation ticket images.

Generates a clean, professional PNG ticket using Pillow.
"""
import io
import base64
import logging
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

from apps.whatsapp.models import WhatsAppReservationRequest
from apps.whatsapp.services.templates.context import ContextBuilder

logger = logging.getLogger(__name__)


class TicketImageService:
    """Generate ticket/comprobante images for reservation confirmations."""

    WIDTH = 400
    PADDING = 24
    LINE_HEIGHT = 28
    TITLE_SIZE = 18
    BODY_SIZE = 14
    BG_COLOR = (255, 255, 255)
    TEXT_COLOR = (33, 33, 33)
    ACCENT_COLOR = (37, 211, 102)  # WhatsApp green
    BORDER_COLOR = (220, 220, 220)

    @classmethod
    def _get_font(cls, size: int):
        """Get font, falling back to default if custom font unavailable."""
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except (OSError, IOError):
            try:
                return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
            except (OSError, IOError):
                return ImageFont.load_default()

    @classmethod
    def _draw_text(cls, draw, x: int, y: int, text: str, font, color=None):
        """Draw single line of text."""
        if color is None:
            color = cls.TEXT_COLOR
        draw.text((x, y), str(text)[:60], fill=color, font=font)
        return y + cls.LINE_HEIGHT

    @classmethod
    def generate_ticket_png(cls, reservation: WhatsAppReservationRequest) -> Optional[bytes]:
        """
        Generate a PNG ticket image for a confirmed reservation.

        Args:
            reservation: WhatsAppReservationRequest instance

        Returns:
            PNG bytes or None on error
        """
        try:
            from apps.whatsapp.services.group_notification_service import GroupNotificationService
            code_obj = GroupNotificationService._get_code_obj(reservation)
            context = ContextBuilder.build(reservation, code_obj)

            # Estimate height
            lines = [
                "COMPROBANTE DE RESERVA",
                "",
                f"Experiencia: {context.get('experiencia', '')}",
                f"Fecha: {context.get('fecha', '')}",
                f"Hora: {context.get('hora', '')}",
                f"Pasajeros: {context.get('pasajeros', '')}",
                f"Total: {context.get('precio', '')}",
                "",
                f"Codigo: {context.get('codigo', '')}",
            ]
            height = cls.PADDING * 2 + len(lines) * cls.LINE_HEIGHT + 40

            img = Image.new('RGB', (cls.WIDTH, height), cls.BG_COLOR)
            draw = ImageDraw.Draw(img)

            font_title = cls._get_font(cls.TITLE_SIZE)
            font_body = cls._get_font(cls.BODY_SIZE)

            y = cls.PADDING

            # Title
            draw.text((cls.PADDING, y), "COMPROBANTE DE RESERVA", fill=cls.ACCENT_COLOR, font=font_title)
            y += cls.LINE_HEIGHT + 8

            # Border line
            draw.line([(cls.PADDING, y), (cls.WIDTH - cls.PADDING, y)], fill=cls.BORDER_COLOR, width=1)
            y += cls.LINE_HEIGHT

            for label, key in [
                ('Experiencia:', 'experiencia'),
                ('Fecha:', 'fecha'),
                ('Hora:', 'hora'),
                ('Pasajeros:', 'pasajeros'),
                ('Total:', 'precio'),
            ]:
                y = cls._draw_text(draw, cls.PADDING, y, f"{label} {context.get(key, 'N/A')}", font_body)
            y += 4
            y = cls._draw_text(draw, cls.PADDING, y, f"Codigo: {context.get('codigo', '')}", font_body)

            # Output to bytes
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            return buffer.getvalue()
        except Exception as e:
            logger.exception(f"Error generating ticket image: {e}")
            return None

    @classmethod
    def generate_ticket_base64(cls, reservation: WhatsAppReservationRequest) -> Optional[str]:
        """
        Generate ticket as base64 string for API transmission.

        Returns:
            Base64 string or None
        """
        png_bytes = cls.generate_ticket_png(reservation)
        if png_bytes:
            return base64.b64encode(png_bytes).decode('utf-8')
        return None
