"""Utility functions for the Tuki platform."""

import os
import uuid
import qrcode
from io import BytesIO
from django.core.files.base import ContentFile
from django.utils import timezone


def generate_unique_code(prefix='', length=8):
    """Generate a unique code with a given prefix."""
    unique_id = uuid.uuid4().hex[:length].upper()
    return f"{prefix}{unique_id}"


def generate_qr_code(data, size=10):
    """Generate a QR code image from the given data."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=size,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    
    return ContentFile(buffer.getvalue())


def get_upload_path(instance, filename):
    """Get the upload path for a file."""
    # Get the model name
    model_name = instance.__class__.__name__.lower()
    
    # Get the current datetime for organizing files
    now = timezone.now()
    date_path = now.strftime('%Y/%m/%d')
    
    # Get file extension
    ext = filename.split('.')[-1]
    
    # Generate a unique filename
    new_filename = f"{uuid.uuid4().hex}.{ext}"
    
    # Return the upload path
    if hasattr(instance, 'tenant_id'):
        return os.path.join(instance.tenant_id, model_name, date_path, new_filename)
    return os.path.join('public', model_name, date_path, new_filename)


def get_current_tenant():
    """Get the current tenant from the thread local storage."""
    from django_tenants.utils import get_current_schema_name
    return get_current_schema_name()


def currency_exchange(amount, from_currency, to_currency):
    """Convert an amount from one currency to another.
    
    Note: This is a placeholder. In a real application, this would
    use an external API or database of exchange rates.
    """
    # Placeholder exchange rates (would use an API in production)
    exchange_rates = {
        'USD': 1.0,
        'EUR': 0.85,
        'CLP': 900.0,
    }
    
    # Convert to USD first if not already
    if from_currency != 'USD':
        amount_usd = amount / exchange_rates[from_currency]
    else:
        amount_usd = amount
    
    # Convert from USD to target currency
    if to_currency != 'USD':
        final_amount = amount_usd * exchange_rates[to_currency]
    else:
        final_amount = amount_usd
    
    return round(final_amount, 2) 