"""
Generate receipt image/PDF for experience reservations (post-payment).
Similar to ticket PDF but tailored for experiences.
"""
import io
import base64
import logging
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class ExperienceReceiptGenerator:
    """Generate receipt image for experience reservations."""

    WIDTH = 400
    PADDING = 24
    LINE_HEIGHT = 26
    TITLE_SIZE = 18
    BODY_SIZE = 14
    BG_COLOR = (255, 255, 255)
    TEXT_COLOR = (33, 33, 33)
    ACCENT_COLOR = (37, 211, 102)
    BORDER_COLOR = (220, 220, 220)

    @classmethod
    def _get_font(cls, size: int):
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except (OSError, IOError):
            try:
                return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
            except (OSError, IOError):
                return ImageFont.load_default()

    @classmethod
    def _draw_text(cls, draw, x: int, y: int, text: str, font, color=None):
        if color is None:
            color = cls.TEXT_COLOR
        draw.text((x, y), str(text)[:70], fill=color, font=font)
        return y + cls.LINE_HEIGHT

    @classmethod
    def generate_receipt_png(cls, order, reservation) -> Optional[bytes]:
        """
        Generate PNG receipt for experience order.

        Args:
            order: Order model instance
            reservation: ExperienceReservation model instance

        Returns:
            PNG bytes or None
        """
        try:
            experience = reservation.experience
            instance = getattr(reservation, 'instance', None)
            start_dt = instance.start_datetime if instance else None
            date_str = start_dt.strftime('%d/%m/%Y') if start_dt else 'N/A'
            time_str = start_dt.strftime('%H:%M') if start_dt else 'N/A'
            participants = reservation.adult_count + reservation.child_count + reservation.infant_count

            total = float(order.total)
            currency = getattr(order, 'currency', 'CLP') or 'CLP'
            total_str = f"${int(total):,} {currency}".replace(',', '.')

            lines_count = 10
            height = cls.PADDING * 2 + lines_count * cls.LINE_HEIGHT + 40
            img = Image.new('RGB', (cls.WIDTH, height), cls.BG_COLOR)
            draw = ImageDraw.Draw(img)

            font_title = cls._get_font(cls.TITLE_SIZE)
            font_body = cls._get_font(cls.BODY_SIZE)

            y = cls.PADDING
            draw.text((cls.PADDING, y), "COMPROBANTE DE RESERVA", fill=cls.ACCENT_COLOR, font=font_title)
            y += cls.LINE_HEIGHT + 8
            draw.line([(cls.PADDING, y), (cls.WIDTH - cls.PADDING, y)], fill=cls.BORDER_COLOR, width=1)
            y += cls.LINE_HEIGHT

            y = cls._draw_text(draw, cls.PADDING, y, f"Experiencia: {experience.title}", font_body)
            y = cls._draw_text(draw, cls.PADDING, y, f"Fecha: {date_str}", font_body)
            y = cls._draw_text(draw, cls.PADDING, y, f"Hora: {time_str}", font_body)
            y = cls._draw_text(draw, cls.PADDING, y, f"Participantes: {participants}", font_body)
            y = cls._draw_text(draw, cls.PADDING, y, f"Total pagado: {total_str}", font_body)
            y += 4
            y = cls._draw_text(draw, cls.PADDING, y, f"N° Reserva: {reservation.reservation_id}", font_body)
            y = cls._draw_text(draw, cls.PADDING, y, f"Orden: {order.order_number}", font_body)

            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            return buffer.getvalue()
        except Exception as e:
            logger.exception(f"Error generating experience receipt: {e}")
            return None

    @classmethod
    def generate_receipt_base64(cls, order, reservation) -> Optional[str]:
        """Generate receipt as base64 for WhatsApp API."""
        png_bytes = cls.generate_receipt_png(order, reservation)
        if png_bytes:
            return base64.b64encode(png_bytes).decode('utf-8')
        return None
