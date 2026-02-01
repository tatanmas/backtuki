"""Management command to sync all WhatsApp data from Node.js service."""
from django.core.management.base import BaseCommand
from apps.whatsapp.services.sync_service import WhatsAppSyncService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Synchronize all WhatsApp data (chats, groups, contacts, profile pictures) from Node.js service to database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--chats-only',
            action='store_true',
            help='Sync only chats (individual chats)',
        )
        parser.add_argument(
            '--groups-only',
            action='store_true',
            help='Sync only groups',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sync even if data seems up to date',
        )

    def handle(self, *args, **options):
        chats_only = options['chats_only']
        groups_only = options['groups_only']
        force = options['force']
        
        self.stdout.write('Starting WhatsApp synchronization...')
        
        try:
            sync_service = WhatsAppSyncService()
            
            if chats_only:
                # Sync only chats
                self.stdout.write('Syncing chats...')
                result = sync_service.sync_all_chats()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\nChats synchronization complete:\n'
                        f'  Created: {result["created"]}\n'
                        f'  Updated: {result["updated"]}\n'
                        f'  Total: {result["total"]}'
                    )
                )
            elif groups_only:
                # Sync only groups
                self.stdout.write('Syncing groups...')
                result = sync_service.sync_all_groups()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\nGroups synchronization complete:\n'
                        f'  Created: {result["created"]}\n'
                        f'  Updated: {result["updated"]}\n'
                        f'  Total: {result["total"]}'
                    )
                )
            else:
                # Sync everything
                self.stdout.write('Syncing all data...')
                
                # Sync chats
                self.stdout.write('Syncing chats...')
                chats_result = sync_service.sync_all_chats()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Chats: {chats_result["created"]} created, {chats_result["updated"]} updated'
                    )
                )
                
                # Sync groups
                self.stdout.write('Syncing groups...')
                groups_result = sync_service.sync_all_groups()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Groups: {groups_result["created"]} created, {groups_result["updated"]} updated'
                    )
                )
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\nSynchronization complete:\n'
                        f'  Chats: {chats_result["created"]} created, {chats_result["updated"]} updated, {chats_result["total"]} total\n'
                        f'  Groups: {groups_result["created"]} created, {groups_result["updated"]} updated, {groups_result["total"]} total'
                    )
                )
        
        except Exception as e:
            logger.exception("Error syncing WhatsApp data")
            self.stdout.write(
                self.style.ERROR(f'Error: {str(e)}')
            )

