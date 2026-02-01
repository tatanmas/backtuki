"""
Service for synchronizing WhatsApp data from Node.js service to database.
"""
import logging
from typing import Dict, List, Optional, Any
from django.utils import timezone
from django.db import transaction
from apps.whatsapp.models import WhatsAppChat
from apps.whatsapp.services.whatsapp_client import WhatsAppWebService

logger = logging.getLogger(__name__)


class WhatsAppSyncService:
    """Service for synchronizing WhatsApp data."""
    
    def __init__(self):
        self.whatsapp_service = WhatsAppWebService()
    
    def sync_all_chats(self) -> Dict[str, int]:
        """
        Sync all chats from Node.js service to database.
        Returns dict with counts: {'created': X, 'updated': Y, 'total': Z}
        """
        try:
            # Get chats from Node.js service
            response = self.whatsapp_service.get_chats()
            chats_data = response.get('chats', [])
            
            logger.info(f"Syncing {len(chats_data)} chats from Node.js service...")
            
            created_count = 0
            updated_count = 0
            
            with transaction.atomic():
                for chat_data in chats_data:
                    result = self.sync_chat(chat_data, commit=False)
                    if result == 'created':
                        created_count += 1
                    elif result == 'updated':
                        updated_count += 1
            
            logger.info(f"Chat sync completed: {created_count} created, {updated_count} updated")
            
            return {
                'created': created_count,
                'updated': updated_count,
                'total': len(chats_data)
            }
        except Exception as e:
            logger.error(f"Error syncing all chats: {e}", exc_info=True)
            raise
    
    def sync_chat(self, chat_data: Dict[str, Any], commit: bool = True) -> Optional[str]:
        """
        Sync a single chat to database.
        Returns 'created', 'updated', or None if error.
        """
        try:
            chat_id = chat_data.get('chat_id')
            if not chat_id:
                logger.warning("Chat data missing chat_id, skipping")
                return None
            
            chat_type = chat_data.get('type', 'individual')
            chat_name = chat_data.get('name', 'Unknown')
            whatsapp_name = chat_data.get('whatsapp_name', '')
            profile_picture_url = chat_data.get('profile_picture_url', '') or ''
            
            # Parse last message timestamp
            last_message_at = None
            last_message = chat_data.get('last_message')
            if last_message and last_message.get('timestamp'):
                try:
                    timestamp = last_message['timestamp']
                    if isinstance(timestamp, (int, float)):
                        if timestamp > 1000000000000:  # Milliseconds
                            last_message_at = timezone.datetime.fromtimestamp(
                                timestamp / 1000, tz=timezone.utc
                            )
                        else:  # Seconds
                            last_message_at = timezone.datetime.fromtimestamp(
                                timestamp, tz=timezone.utc
                            )
                except (ValueError, TypeError, OSError) as e:
                    logger.warning(f"Could not parse timestamp for chat {chat_id}: {e}")
            
            # For groups, get additional info
            defaults = {
                'name': chat_name,
                'type': chat_type,
                'is_active': True,
                'whatsapp_name': whatsapp_name,
                'profile_picture_url': profile_picture_url,
                'unread_count': chat_data.get('unread_count', 0) or 0,
                'last_message_at': last_message_at
            }
            
            if chat_type == 'group':
                defaults['group_description'] = chat_data.get('description', '') or ''
                defaults['participants'] = chat_data.get('participants', []) or []
            
            # Get or create chat
            chat, created = WhatsAppChat.objects.get_or_create(
                chat_id=chat_id,
                defaults=defaults
            )
            
            if created:
                logger.info(f"Created chat: {chat_name} ({chat_type})")
                return 'created'
            else:
                # Update existing chat
                update_fields = []
                
                # Update name if better (not Unknown, longer, or starts with +)
                new_name = chat_data.get('name')
                if new_name and new_name != chat.name and new_name != 'Unknown':
                    if (chat.name == 'Unknown' or 
                        'Unknown' in chat.name or
                        len(new_name) > len(chat.name) or
                        (new_name.startswith('+') and not chat.name.startswith('+'))):
                        chat.name = new_name
                        update_fields.append('name')
                
                # Update type if changed
                if chat.type != chat_type:
                    chat.type = chat_type
                    update_fields.append('type')
                
                # Update WhatsApp name
                if whatsapp_name and whatsapp_name != chat.whatsapp_name:
                    chat.whatsapp_name = whatsapp_name
                    update_fields.append('whatsapp_name')
                
                # Update profile picture
                if profile_picture_url and profile_picture_url != chat.profile_picture_url:
                    chat.profile_picture_url = profile_picture_url
                    update_fields.append('profile_picture_url')
                
                # Update unread count
                unread_count = chat_data.get('unread_count', 0)
                if unread_count is not None and unread_count != chat.unread_count:
                    chat.unread_count = unread_count
                    update_fields.append('unread_count')
                
                # Update last message time if newer
                if last_message_at and (
                    not chat.last_message_at or last_message_at > chat.last_message_at
                ):
                    chat.last_message_at = last_message_at
                    update_fields.append('last_message_at')
                
                # For groups, update description and participants
                if chat_type == 'group':
                    description = chat_data.get('description', '')
                    if description and description != chat.group_description:
                        chat.group_description = description
                        update_fields.append('group_description')
                    
                    participants = chat_data.get('participants', [])
                    if participants:
                        chat.participants = participants
                        update_fields.append('participants')
                
                if update_fields:
                    if commit:
                        chat.save(update_fields=update_fields)
                    else:
                        # In transaction, will be saved when transaction commits
                        chat.save(update_fields=update_fields)
                    logger.info(f"Updated chat: {chat_name} ({', '.join(update_fields)})")
                    return 'updated'
                
                return None
                
        except Exception as e:
            logger.error(f"Error syncing chat {chat_data.get('chat_id', 'unknown')}: {e}", exc_info=True)
            return None
    
    def sync_all_groups(self) -> Dict[str, int]:
        """
        Sync all groups from Node.js service to database.
        Returns dict with counts: {'created': X, 'updated': Y, 'total': Z}
        """
        try:
            # Get groups from Node.js service
            response = self.whatsapp_service.get_groups()
            groups_data = response.get('groups', [])
            
            logger.info(f"Syncing {len(groups_data)} groups from Node.js service...")
            
            created_count = 0
            updated_count = 0
            
            with transaction.atomic():
                for group_data in groups_data:
                    # Asegurar que el tipo sea 'group' para datos de grupos
                    group_data['type'] = 'group'
                    result = self.sync_chat(group_data, commit=False)
                    if result == 'created':
                        created_count += 1
                    elif result == 'updated':
                        updated_count += 1
            
            logger.info(f"Group sync completed: {created_count} created, {updated_count} updated")
            
            return {
                'created': created_count,
                'updated': updated_count,
                'total': len(groups_data)
            }
        except Exception as e:
            logger.error(f"Error syncing all groups: {e}", exc_info=True)
            raise
    
    def sync_group_participants(self, group_id: str) -> bool:
        """
        Sync participants for a specific group.
        Returns True if successful, False otherwise.
        """
        try:
            # Get group info from Node.js service
            group_info = self.whatsapp_service.get_group_info(group_id)
            
            if not group_info:
                logger.warning(f"Group info not found for {group_id}")
                return False
            
            # Get group chat from database
            try:
                group_chat = WhatsAppChat.objects.get(chat_id=group_id, type='group')
            except WhatsAppChat.DoesNotExist:
                logger.warning(f"Group {group_id} not found in database")
                return False
            
            # Update participants
            participants = group_info.get('participants', [])
            if participants:
                group_chat.participants = participants
                group_chat.save(update_fields=['participants'])
                logger.info(f"Updated participants for group {group_id}: {len(participants)} participants")
                return True
            
            return False
        except Exception as e:
            logger.error(f"Error syncing group participants for {group_id}: {e}", exc_info=True)
            return False
    
    def sync_chat_messages(self, chat_id: str, limit: int = 1000) -> Dict[str, int]:
        """
        Sync message history for a specific chat.
        Returns dict with counts: {'created': X, 'updated': Y, 'total': Z}
        """
        from apps.whatsapp.models import WhatsAppMessage, WhatsAppChat
        from django.db import transaction
        
        try:
            # Get messages from Node.js service
            response = self.whatsapp_service.get_chat_messages(chat_id, limit=limit)
            messages_data = response.get('messages', [])
            
            logger.info(f"Syncing {len(messages_data)} messages for chat {chat_id}...")
            
            # Get or create chat
            try:
                chat = WhatsAppChat.objects.get(chat_id=chat_id)
            except WhatsAppChat.DoesNotExist:
                logger.warning(f"Chat {chat_id} not found in database, skipping message sync")
                return {'created': 0, 'updated': 0, 'total': 0}
            
            created_count = 0
            updated_count = 0
            
            with transaction.atomic():
                for msg_data in messages_data:
                    whatsapp_id = msg_data.get('whatsapp_id') or msg_data.get('id')
                    if not whatsapp_id:
                        logger.warning(f"Message missing whatsapp_id, skipping")
                        continue
                    
                    # Check if message already exists (idempotency)
                    existing_message = WhatsAppMessage.objects.filter(whatsapp_id=whatsapp_id).first()
                    
                    if existing_message:
                        # Message already exists, skip
                        continue
                    
                    # Parse timestamp
                    raw_timestamp = msg_data.get('timestamp')
                    message_timestamp = timezone.now()
                    
                    if isinstance(raw_timestamp, (int, float)) and raw_timestamp > 0:
                        try:
                            if raw_timestamp > 10000000000:  # Milliseconds
                                message_timestamp = timezone.datetime.fromtimestamp(
                                    raw_timestamp / 1000, tz=timezone.utc
                                )
                            else:  # Seconds
                                message_timestamp = timezone.datetime.fromtimestamp(
                                    raw_timestamp, tz=timezone.utc
                                )
                        except (ValueError, OSError) as e:
                            logger.warning(f"Could not parse timestamp {raw_timestamp}: {e}")
                            message_timestamp = timezone.now()
                    
                    # Prepare metadata for group messages
                    message_metadata = {}
                    if msg_data.get('chat_type') == 'group' and msg_data.get('sender_name'):
                        message_metadata['sender_name'] = msg_data.get('sender_name')
                    if msg_data.get('chat_type') == 'group' and msg_data.get('sender_phone'):
                        message_metadata['sender_phone'] = msg_data.get('sender_phone')
                    
                    # Create message
                    WhatsAppMessage.objects.create(
                        whatsapp_id=whatsapp_id,
                        phone=msg_data.get('phone', ''),
                        type=msg_data.get('type', 'in'),
                        content=msg_data.get('content', ''),
                        timestamp=message_timestamp,
                        chat=chat,
                        is_automated=False,
                        metadata=message_metadata if message_metadata else {}
                    )
                    created_count += 1
            
            logger.info(f"Message sync completed for {chat_id}: {created_count} created")
            
            return {
                'created': created_count,
                'updated': updated_count,
                'total': len(messages_data)
            }
        except Exception as e:
            logger.error(f"Error syncing messages for chat {chat_id}: {e}", exc_info=True)
            raise

