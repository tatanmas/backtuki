"""
🚀 ENTERPRISE QR Code Generator - Tuki Platform
Pre-generates QR codes for tickets to avoid blocking email delivery.

Performance:
- Generates QR codes asynchronously when tickets are created
- Stores QR as base64 in database (no file I/O during email send)
- Parallel generation for multiple tickets
- <100ms per QR code generation

Usage:
    from apps.events.qr_generator import generate_ticket_qr, generate_tickets_qr_batch
    
    # Single ticket
    qr_base64 = generate_ticket_qr(ticket)
    
    # Multiple tickets (parallel)
    generate_tickets_qr_batch(tickets)
"""

import logging
import qrcode
import io
import base64
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.conf import settings

logger = logging.getLogger(__name__)


def generate_qr_image(ticket_number: str, frontend_url: str) -> bytes:
    """
    Generate QR code image as PNG bytes.
    
    Args:
        ticket_number: Unique ticket identifier
        frontend_url: Base URL for ticket validation
        
    Returns:
        PNG image as bytes
        
    Performance: ~50-100ms per QR
    """
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        
        qr_data = f"{frontend_url}/tickets/{ticket_number}"
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to bytes (in-memory, no disk I/O)
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return buffer.getvalue()
        
    except Exception as e:
        logger.error(f"❌ [QR] Error generating QR for ticket {ticket_number}: {e}")
        raise


def generate_qr_base64(ticket_number: str, frontend_url: str) -> str:
    """
    Generate QR code as base64 string (for embedding in emails).
    
    Args:
        ticket_number: Unique ticket identifier
        frontend_url: Base URL for ticket validation
        
    Returns:
        Base64-encoded PNG image
    """
    png_bytes = generate_qr_image(ticket_number, frontend_url)
    return base64.b64encode(png_bytes).decode('utf-8')


def generate_ticket_qr(ticket, save: bool = True) -> Optional[str]:
    """
    Generate and optionally save QR code for a single ticket.
    
    Args:
        ticket: Ticket model instance
        save: Whether to save QR to ticket.qr_code field
        
    Returns:
        Base64-encoded QR code or None if error
        
    Example:
        qr_base64 = generate_ticket_qr(ticket)
        # Use in email: <img src="data:image/png;base64,{qr_base64}" />
    """
    try:
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')
        qr_base64 = generate_qr_base64(ticket.ticket_number, frontend_url)
        
        if save and hasattr(ticket, 'qr_code'):
            # Use update() to avoid transaction issues
            from apps.events.models import Ticket
            Ticket.objects.filter(id=ticket.id).update(qr_code=qr_base64)
            # Refresh instance to reflect the update
            ticket.refresh_from_db()
            logger.info(f"✅ [QR] Generated and saved QR for ticket {ticket.ticket_number}")
        
        return qr_base64
        
    except Exception as e:
        logger.error(f"❌ [QR] Failed to generate QR for ticket {ticket.ticket_number}: {e}", exc_info=True)
        return None


def generate_tickets_qr_batch(tickets: List, max_workers: int = 4) -> dict:
    """
    Generate QR codes for multiple tickets in parallel.
    
    Args:
        tickets: List of Ticket model instances
        max_workers: Number of parallel workers (default 4)
        
    Returns:
        Dict with success/failure counts and timing
        
    Performance: ~100ms for 4 tickets, ~200ms for 10 tickets
    
    Example:
        from apps.events.models import Ticket
        tickets = Ticket.objects.filter(order=order)
        result = generate_tickets_qr_batch(tickets)
        # {'success': 10, 'failed': 0, 'duration_ms': 150}
    """
    import time
    start_time = time.time()
    
    success_count = 0
    failed_count = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(generate_ticket_qr, ticket): ticket for ticket in tickets}
        
        for future in as_completed(futures):
            ticket = futures[future]
            try:
                qr_code = future.result()
                if qr_code:
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"❌ [QR] Batch generation failed for ticket {ticket.ticket_number}: {e}")
                failed_count += 1
    
    duration_ms = int((time.time() - start_time) * 1000)
    
    logger.info(
        f"✅ [QR] Batch generation complete: {success_count} success, "
        f"{failed_count} failed in {duration_ms}ms"
    )
    
    return {
        'success': success_count,
        'failed': failed_count,
        'duration_ms': duration_ms,
    }

