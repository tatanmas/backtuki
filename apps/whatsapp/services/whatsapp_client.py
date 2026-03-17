"""Client for communicating with WhatsApp Web service (Node.js)."""
import os
import requests
import logging
from typing import Optional, Tuple
from django.conf import settings

logger = logging.getLogger(__name__)


class WhatsAppWebService:
    """Client for WhatsApp Web service."""
    
    def __init__(self):
        # Use environment variable or settings, with smart defaults
        # In Docker compose, use service name; locally, use localhost
        if hasattr(settings, 'WHATSAPP_SERVICE_URL'):
            self.base_url = settings.WHATSAPP_SERVICE_URL
        else:
            # Try to detect if we're in Docker by checking if we can resolve the service name
            # Default to service name for Docker, localhost for local dev
            import socket
            try:
                # Try to resolve Docker service name (will fail if not in Docker network)
                socket.gethostbyname('tuki-whatsapp-service')
                self.base_url = 'http://tuki-whatsapp-service:3001'
            except socket.gaierror:
                # Not in Docker network, use localhost
                self.base_url = 'http://localhost:3001'
        # Configurable timeout; default 25s so Chromium/Puppeteer has time to respond in production
        self.timeout = getattr(settings, 'WHATSAPP_SERVICE_TIMEOUT', 25)
    
    @staticmethod
    def clean_phone_number(phone: str) -> str:
        """
        Clean phone number for WhatsApp API.
        Removes spaces, dashes, plus signs, and other non-numeric characters.
        
        Args:
            phone: Raw phone number
            
        Returns:
            Cleaned phone number (digits only)
        """
        import re
        # Remove all non-numeric characters
        cleaned = re.sub(r'\D', '', phone)
        return cleaned
    
    def send_message(self, phone_number: str, message: str, group_id: str = None, chat_id: str = None) -> dict:
        """
        Send message via WhatsApp service.
        
        Args:
            phone_number: Phone number (e.g., '56912345678' or '+56 9 1234 5678')
            message: Message text
            group_id: Optional group ID for group messages (e.g., '120363123456789012@g.us')
            chat_id: Optional chat ID - required for @lid contacts (e.g., '37881745801364@lid')
            
        Returns:
            dict with success status and message_id
        """
        try:
            url = f"{self.base_url}/api/send-message"
            payload = {
                'text': message
            }
            
            if group_id:
                payload['groupId'] = group_id
            elif chat_id and '@lid' in str(chat_id):
                payload['chatId'] = chat_id
            else:
                clean_phone = self.clean_phone_number(phone_number)
                payload['phone'] = clean_phone
                logger.debug(f"Sending to phone: {phone_number} -> {clean_phone}")
            
            response = requests.post(url, json=payload, timeout=self.timeout)
            if not response.ok:
                try:
                    body = response.json()
                    service_error = body.get("error") or body.get("message") or response.text
                except Exception:
                    service_error = response.text or response.reason
                msg = (service_error or response.reason or "Unknown error").strip()
                logger.error("Error sending WhatsApp message: %s %s", response.status_code, msg)
                raise requests.exceptions.HTTPError(
                    f"{response.status_code} {response.reason}: {msg}",
                    response=response,
                )
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error("Error sending WhatsApp message: %s", e)
            raise

    def send_media(
        self,
        phone_number: str,
        media_base64: str,
        mimetype: str = 'image/png',
        filename: str = 'ticket.png',
        caption: str = '',
        group_id: str = None,
        chat_id: str = None
    ) -> dict:
        """
        Send media (image/document) via WhatsApp service.

        Args:
            phone_number: Phone number or chat ID
            media_base64: Base64-encoded media data
            mimetype: MIME type (default: image/png)
            filename: Filename for document
            caption: Optional caption
            group_id: Optional group ID for group messages
            chat_id: Optional chat ID for @lid contacts

        Returns:
            dict with success status
        """
        try:
            url = f"{self.base_url}/api/send-media"
            payload = {
                'mediaBase64': media_base64,
                'mimetype': mimetype,
                'filename': filename,
                'caption': caption,
            }
            if group_id:
                payload['groupId'] = group_id
            elif chat_id and '@lid' in str(chat_id):
                payload['chatId'] = chat_id
            else:
                payload['phone'] = self.clean_phone_number(phone_number)

            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending WhatsApp media: {e}")
            raise

    def get_status(self) -> dict:
        """Get WhatsApp service status."""
        try:
            url = f"{self.base_url}/api/status"
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting WhatsApp status: {e}")
            return {'isReady': False, 'error': str(e)}
    
    def get_qr_code(self) -> str:
        """Get current QR code. Returns None if service has no QR (e.g. waiting after disconnect)."""
        try:
            url = f"{self.base_url}/api/qr"
            response = requests.get(url, timeout=self.timeout)
            # Service returns 200 with qr: null when no QR (no longer 404)
            data = response.json() if response.ok else {}
            if not response.ok:
                logger.warning(f"get_qr_code: service returned {response.status_code}")
                return None
            return data.get('qr')
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting QR code: {e}")
            return None

    def request_new_qr(self) -> Tuple[bool, Optional[str]]:
        """
        Ask the WhatsApp service to re-initialize and emit a new QR (e.g. after disconnect).
        Returns (success, error_message). error_message is set when service returns 404 (endpoint not found)
        or 503 (e.g. profile locked) with a user-facing message.
        """
        try:
            url = f"{self.base_url}/api/request-new-qr"
            response = requests.post(url, timeout=self.timeout)
            if response.status_code == 404:
                logger.warning(
                    "WhatsApp service returned 404 for POST /api/request-new-qr. "
                    "Reconstruye el contenedor: docker compose build whatsapp-service && docker compose up -d whatsapp-service"
                )
                return False, "El servicio WhatsApp no tiene la ruta request-new-qr. Reinicia el contenedor whatsapp-service."
            if response.status_code in (500, 503):
                try:
                    body = response.json()
                    err = body.get("message") or body.get("error") or response.text or response.reason
                    if isinstance(err, str) and err.strip():
                        return False, err.strip()
                except Exception:
                    pass
                return False, response.reason or "El servicio WhatsApp no pudo generar un nuevo QR."
            response.raise_for_status()
            return True, None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error requesting new QR: {e}")
            return False, str(e)

    def disconnect(self) -> bool:
        """Disconnect WhatsApp session."""
        try:
            url = f"{self.base_url}/api/disconnect"
            response = requests.post(url, timeout=self.timeout)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Error disconnecting WhatsApp: {e}")
            return False
    
    def get_groups(self) -> dict:
        """Get all WhatsApp groups."""
        try:
            url = f"{self.base_url}/api/groups"
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting groups: {e}")
            return {'groups': []}
    
    def get_chats(self) -> dict:
        """Get all WhatsApp chats (individual and groups). Returns empty on 503/unavailable."""
        try:
            url = f"{self.base_url}/api/chats"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"get_chats failed (503/unavailable is normal): {e}")
            return {'chats': []}
    
    def get_group_info(self, group_id: str) -> dict:
        """Get detailed information about a specific group."""
        try:
            url = f"{self.base_url}/api/group-info/{group_id}"
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting group info: {e}")
            raise
    
    def _get_raw(self, url: str):
        """GET raw response (for binary like profile pictures). Returns Response or None."""
        try:
            return requests.get(url, timeout=self.timeout, stream=False)
        except requests.exceptions.RequestException as e:
            logger.error(f"GET raw failed {url}: {e}")
            return None

    def get_chat_messages(self, chat_id: str, limit: int = 1000) -> dict:
        """Get message history for a specific chat."""
        try:
            url = f"{self.base_url}/api/chats/{chat_id}/messages"
            params = {'limit': limit}
            response = requests.get(url, params=params, timeout=120)  # Timeout largo: sync con muchos mensajes + grupos
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting chat messages for {chat_id}: {e}")
            return {'messages': [], 'total': 0}

    def check_saved_contacts(self, participant_ids: list) -> dict:
        """
        Check which participant IDs are saved contacts (in phone address book).
        Returns dict mapping participant_id -> bool (True if saved contact).
        """
        if not participant_ids:
            return {}
        try:
            url = f"{self.base_url}/api/check-saved-contacts"
            response = requests.post(url, json={'ids': participant_ids}, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error checking saved contacts: {e}")
            return {pid: False for pid in participant_ids}

