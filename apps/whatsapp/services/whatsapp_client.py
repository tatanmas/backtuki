"""Client for communicating with WhatsApp Web service (Node.js)."""
import os
import requests
import logging
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
        self.timeout = 10
    
    def send_message(self, phone_number: str, message: str, group_id: str = None) -> dict:
        """
        Send message via WhatsApp service.
        
        Args:
            phone_number: Phone number (e.g., '56912345678')
            message: Message text
            group_id: Optional group ID for group messages (e.g., '120363123456789012@g.us')
            
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
                # Para grupos, no necesitamos phone_number
            else:
                payload['phone'] = phone_number
            
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending WhatsApp message: {e}")
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
        """Get current QR code."""
        try:
            url = f"{self.base_url}/api/qr"
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data.get('qr')
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting QR code: {e}")
            return None
    
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
        """Get all WhatsApp chats (individual and groups)."""
        try:
            url = f"{self.base_url}/api/chats"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting chats: {e}")
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
    
    def get_chat_messages(self, chat_id: str, limit: int = 1000) -> dict:
        """Get message history for a specific chat."""
        try:
            url = f"{self.base_url}/api/chats/{chat_id}/messages"
            params = {'limit': limit}
            response = requests.get(url, params=params, timeout=60)  # Timeout más largo para muchos mensajes
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting chat messages for {chat_id}: {e}")
            return {'messages': [], 'total': 0}

