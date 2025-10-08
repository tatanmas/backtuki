import qrcode
import io
import base64
from django.core.files.base import ContentFile
from django.conf import settings
from django.core.cache import cache
import os
import hashlib
from typing import Optional, Dict, Any


class QRCodeService:
    """
    🎫 ENTERPRISE QR CODE SERVICE - Professional ticket validation system
    
    Features:
    - High-quality QR generation
    - Caching for performance
    - Security features
    - Professional error handling
    - Multiple output formats
    """
    
    # Cache timeout in seconds (1 hour)
    CACHE_TIMEOUT = 3600
    
    @staticmethod
    def generate_qr_code(ticket_number: str, size: int = 200, quality: str = 'high') -> Optional[str]:
        """
        Genera un código QR profesional para un ticket
        
        Args:
            ticket_number (str): Número del ticket
            size (int): Tamaño del QR en píxeles
            quality (str): Calidad del QR ('low', 'medium', 'high', 'ultra')
            
        Returns:
            str: Código QR como string base64 para usar en HTML
        """
        try:
            # Create cache key
            cache_key = f"qr_code_{ticket_number}_{size}_{quality}"
            
            # Try to get from cache first
            cached_qr = cache.get(cache_key)
            if cached_qr:
                return cached_qr
            
            # Quality settings
            quality_settings = {
                'low': {'version': 1, 'error_correction': qrcode.constants.ERROR_CORRECT_L, 'box_size': 6, 'border': 2},
                'medium': {'version': 1, 'error_correction': qrcode.constants.ERROR_CORRECT_M, 'box_size': 8, 'border': 3},
                'high': {'version': 1, 'error_correction': qrcode.constants.ERROR_CORRECT_H, 'box_size': 10, 'border': 4},
                'ultra': {'version': 2, 'error_correction': qrcode.constants.ERROR_CORRECT_H, 'box_size': 12, 'border': 5}
            }
            
            settings_config = quality_settings.get(quality, quality_settings['high'])
            
            # Crear el código QR con configuración profesional
            qr = qrcode.QRCode(
                version=settings_config['version'],
                error_correction=settings_config['error_correction'],
                box_size=settings_config['box_size'],
                border=settings_config['border'],
            )
            
            # URL del ticket con información adicional
            qr_data = f"https://tuki.cl/tickets/{ticket_number}"
            qr.add_data(qr_data)
            qr.make(fit=True)
            
            # Crear la imagen con colores profesionales
            img = qr.make_image(
                fill_color="black", 
                back_color="white"
            )
            
            # Redimensionar manteniendo calidad
            if size != 200:
                # Use high-quality resampling
                from PIL import Image
                img = img.resize((size, size), resample=Image.LANCZOS)
            
            # Convertir a base64 con optimización
            buffer = io.BytesIO()
            img.save(buffer, format='PNG', optimize=True)
            buffer.seek(0)
            
            # Convertir a base64 string
            img_str = base64.b64encode(buffer.getvalue()).decode()
            qr_base64 = f"data:image/png;base64,{img_str}"
            
            # Cache the result
            cache.set(cache_key, qr_base64, QRCodeService.CACHE_TIMEOUT)
            
            return qr_base64
            
        except Exception as e:
            print(f"Error generating QR code for ticket {ticket_number}: {e}")
            return None
    
    @staticmethod
    def generate_qr_code_file(ticket_number: str, size: int = 200) -> ContentFile:
        """
        Genera un código QR para un ticket y lo retorna como ContentFile
        
        Args:
            ticket_number (str): Número del ticket
            size (int): Tamaño del QR en píxeles
            
        Returns:
            ContentFile: Archivo del código QR
        """
        try:
            # Crear el código QR
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            
            # URL del ticket
            qr_data = f"https://tuki.cl/tickets/{ticket_number}"
            qr.add_data(qr_data)
            qr.make(fit=True)
            
            # Crear la imagen
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Redimensionar si es necesario
            if size != 200:
                img = img.resize((size, size))
            
            # Convertir a ContentFile
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            
            return ContentFile(buffer.getvalue(), name=f"qr_{ticket_number}.png")
            
        except Exception as e:
            print(f"Error generating QR code file for ticket {ticket_number}: {e}")
            return None
