"""Utility functions for the Tuki platform."""

import os
import uuid
import qrcode
from io import BytesIO
from django.core.files.base import ContentFile
from django.utils import timezone
from django.core.files.storage import default_storage


def generate_unique_code(prefix='', length=8):
    """Generate a unique code with a given prefix."""
    unique_id = uuid.uuid4().hex[:length].upper()
    return f"{prefix}{unique_id}"


def generate_username(email):
    """Generate a unique username from email."""
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    base_username = email.split('@')[0]
    username = base_username
    counter = 1
    
    while User.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1
    
    return username


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


def generate_unique_filename(original_filename):
    """Generate a unique filename to avoid conflicts."""
    name, ext = os.path.splitext(original_filename)
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    return f"{name}_{timestamp}_{unique_id}{ext}"


def get_upload_path(instance, filename):
    """
    Generate upload path for files.
    
    Args:
        instance: The model instance
        filename: The original filename
    
    Returns:
        str: The upload path
    """
    # Get the model name
    model_name = instance._meta.model_name.lower()
    
    # Get current date for organization
    date_path = timezone.now().strftime('%Y/%m/%d')
    
    # Generate unique filename
    new_filename = generate_unique_filename(filename)
    
    # If instance has organizer, include it in the path
    if hasattr(instance, 'organizer'):
        return os.path.join(instance.organizer.slug, model_name, date_path, new_filename)
    
    # Fallback path
    return os.path.join(model_name, date_path, new_filename)


def get_current_organizer(request):
    """Get the current organizer from the request."""
    if request.user.is_authenticated and hasattr(request.user, 'organizer_roles'):
        organizer_user = request.user.organizer_roles.first()
        if organizer_user:
            return organizer_user.organizer
    return None


def save_file_to_storage(file_content, file_path):
    """
    Save file content to storage.
    
    Args:
        file_content: The file content (bytes or string)
        file_path: The path where to save the file
    
    Returns:
        str: The saved file path
    """
    if isinstance(file_content, str):
        file_content = file_content.encode('utf-8')
    
    saved_path = default_storage.save(file_path, ContentFile(file_content))
    return saved_path


def delete_file_from_storage(file_path):
    """
    Delete file from storage.
    
    Args:
        file_path: The path of the file to delete
    
    Returns:
        bool: True if file was deleted, False otherwise
    """
    if default_storage.exists(file_path):
        default_storage.delete(file_path)
        return True
    return False


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