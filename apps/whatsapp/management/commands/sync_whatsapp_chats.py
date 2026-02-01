"""Management command to sync WhatsApp chats from Node.js service."""
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.whatsapp.models import WhatsAppChat
from apps.whatsapp.services.whatsapp_client import WhatsAppWebService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Synchronize WhatsApp chats from Node.js service to database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write('Starting WhatsApp chats synchronization...')
        
        try:
            # Get chats from Node.js service
            service = WhatsAppWebService()
            
            # Call Node.js /api/chats endpoint
            import requests
            from django.conf import settings
            
            whatsapp_service_url = getattr(settings, 'WHATSAPP_SERVICE_URL', 'http://localhost:3001')
            response = requests.get(f'{whatsapp_service_url}/api/chats', timeout=10)
            
            if response.status_code != 200:
                self.stdout.write(
                    self.style.ERROR(f'Error fetching chats: {response.status_code}')
                )
                return
            
            chats_data = response.json().get('chats', [])
            self.stdout.write(f'Found {len(chats_data)} chats in Node.js service')
            
            synced_count = 0
            created_count = 0
            updated_count = 0
            
            for chat_data in chats_data:
                chat_id = chat_data.get('chat_id')
                chat_name = chat_data.get('name', 'Unknown')
                chat_type = chat_data.get('type', 'individual')
                last_message = chat_data.get('last_message')
                
                if not chat_id:
                    continue
                
                # Parse timestamp del último mensaje
                last_message_at = None
                if last_message and isinstance(last_message.get('timestamp'), (int, float)):
                    try:
                        timestamp = last_message['timestamp']
                        # Si el timestamp está en milisegundos, convertir a datetime
                        if timestamp > 1000000000000:  # Milisegundos
                            last_message_at = timezone.datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
                        else:  # Segundos
                            last_message_at = timezone.datetime.fromtimestamp(timestamp, tz=timezone.utc)
                    except (ValueError, TypeError, OSError) as e:
                        logger.warning(f"Could not parse timestamp for chat {chat_id}: {e}")
                
                # Get or create chat
                defaults = {
                    'name': chat_name,
                    'type': chat_type,
                    'is_active': True,
                    'last_message_at': last_message_at,
                    'whatsapp_name': chat_data.get('whatsapp_name', '') or '',
                    'profile_picture_url': chat_data.get('profile_picture_url', '') or '',
                    'unread_count': chat_data.get('unread_count', 0) or 0
                }
                
                # Para grupos, agregar información adicional
                if chat_type == 'group':
                    defaults['group_description'] = chat_data.get('description', '') or ''
                    defaults['participants'] = chat_data.get('participants', []) or []
                
                chat, created = WhatsAppChat.objects.get_or_create(
                    chat_id=chat_id,
                    defaults=defaults
                )
                
                if created:
                    created_count += 1
                    if not dry_run:
                        self.stdout.write(
                            self.style.SUCCESS(f'Created chat: {chat_name} ({chat_type})')
                        )
                else:
                    # Update existing chat
                    update_fields = []
                    if chat.name != chat_name:
                        chat.name = chat_name
                        update_fields.append('name')
                    if chat.type != chat_type:
                        chat.type = chat_type
                        update_fields.append('type')
                    
                    if last_message_at and (not chat.last_message_at or last_message_at > chat.last_message_at):
                        chat.last_message_at = last_message_at
                        update_fields.append('last_message_at')
                    
                    # Actualizar información adicional
                    if chat_data.get('whatsapp_name'):
                        chat.whatsapp_name = chat_data['whatsapp_name']
                        update_fields.append('whatsapp_name')
                    if chat_data.get('profile_picture_url'):
                        chat.profile_picture_url = chat_data['profile_picture_url']
                        update_fields.append('profile_picture_url')
                    if chat_data.get('unread_count') is not None:
                        chat.unread_count = chat_data['unread_count']
                        update_fields.append('unread_count')
                    
                    # Para grupos, actualizar información adicional
                    if chat_type == 'group':
                        if chat_data.get('description'):
                            chat.group_description = chat_data['description']
                            update_fields.append('group_description')
                        if chat_data.get('participants'):
                            chat.participants = chat_data['participants']
                            update_fields.append('participants')
                    
                    if update_fields:
                        updated_count += 1
                        if not dry_run:
                            chat.save(update_fields=update_fields)
                            self.stdout.write(
                                self.style.SUCCESS(f'Updated chat: {chat_name}')
                            )
                
                synced_count += 1
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nSynchronization complete:\n'
                    f'  Total synced: {synced_count}\n'
                    f'  Created: {created_count}\n'
                    f'  Updated: {updated_count}'
                )
            )
            
            if dry_run:
                self.stdout.write(
                    self.style.WARNING('\nDRY RUN - No changes were made')
                )
        
        except Exception as e:
            logger.exception("Error syncing WhatsApp chats")
            self.stdout.write(
                self.style.ERROR(f'Error: {str(e)}')
            )

