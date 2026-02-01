"""Management command to sync WhatsApp messages from Node.js service."""
from django.core.management.base import BaseCommand
from apps.whatsapp.services.sync_service import WhatsAppSyncService
from apps.whatsapp.models import WhatsAppChat
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Synchronize WhatsApp message history from Node.js service to database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--chat-id',
            type=str,
            help='Sync messages for a specific chat ID only',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=1000,
            help='Maximum number of messages to sync per chat (default: 1000)',
        )
        parser.add_argument(
            '--all-chats',
            action='store_true',
            help='Sync messages for all chats',
        )

    def handle(self, *args, **options):
        sync_service = WhatsAppSyncService()
        chat_id = options.get('chat_id')
        limit = options.get('limit', 1000)
        all_chats = options.get('all_chats', False)
        
        if chat_id:
            # Sync specific chat
            self.stdout.write(f'Syncing messages for chat {chat_id}...')
            try:
                result = sync_service.sync_chat_messages(chat_id, limit=limit)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully synced {result["created"]} messages for chat {chat_id}'
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error syncing messages for chat {chat_id}: {e}')
                )
        elif all_chats:
            # Sync all chats
            self.stdout.write('Syncing messages for all chats...')
            chats = WhatsAppChat.objects.filter(is_active=True)
            total_created = 0
            
            for chat in chats:
                try:
                    result = sync_service.sync_chat_messages(chat.chat_id, limit=limit)
                    total_created += result['created']
                    self.stdout.write(
                        f'  Chat {chat.name}: {result["created"]} messages created'
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'  Error syncing chat {chat.chat_id}: {e}')
                    )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Total messages synced: {total_created}'
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    'Please specify --chat-id or --all-chats'
                )
            )

